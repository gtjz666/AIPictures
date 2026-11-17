@tool
extends RefCounted
## Generates native, editable scenes in a NEW directory, never a user's scene.
const Builder: GDScript = preload("game_builder.gd")
const Model: GDScript = preload("game_model.gd")
const Assets: GDScript = preload("game_assets.gd")
const PRESETS: Dictionary = {"empty":"空白2D","basic":"基础2D","platformer":"平台跳跃","runner":"横版跑酷"}


static func create(folder: String, preset: String, set_main: bool = false) -> Dictionary:
	if not folder.begins_with("res://") or ".." in folder or folder.trim_prefix("res://").is_empty() or not PRESETS.has(preset): return {"error":"请选择项目内的新文件夹与2D模板"}
	if DirAccess.dir_exists_absolute(folder) or FileAccess.file_exists(folder): return {"error":"目录已存在；请选择新名称，现有文件不会覆盖"}
	if DirAccess.make_dir_recursive_absolute(folder) != OK: return {"error":"无法创建模板目录"}
	var game_path: String = folder.path_join("Game.tscn")
	var data: Dictionary = Model.preset() if preset == "runner" else Model.scene_preset()
	# Menus are native scenes; retain the old HUD module/API but hide its UI.
	data["edges"] = data["edges"].filter(func(edge: Dictionary) -> bool: return edge["from"] != "hud" and edge["to"] != "hud" and (edge["from"] != "input" or preset == "runner" and int(edge["from_port"]) == 0))
	Model.by_kind(data,"session")["params"]["save_key"] = "game_"+folder.sha256_text().left(16)+"_"+str(Time.get_ticks_usec())
	var error: String = Builder.create_scene(data,game_path)
	if not error.is_empty(): return {"error":error,"folder":folder}
	var game: Node2D = (load(game_path) as PackedScene).instantiate() as Node2D
	var modules: String = game.get_script().resource_path.get_base_dir()
	var config: Dictionary = {"key":Model.by_kind(data,"session")["params"]["save_key"],"menu_scene":folder.path_join("MainMenu.tscn"),"game_scene":game_path,"settings_scene":folder.path_join("SettingsMenu.tscn"),"save_scene":folder.path_join("SaveLoadMenu.tscn"),"pause_scene":folder.path_join("PauseMenu.tscn"),"over_scene":folder.path_join("GameOver.tscn"),"actor":"Runner" if preset == "runner" else "Player","auto_start":true,"native_menus":true,"preset":preset}
	game.set("framework",config)
	if preset in ["basic","platformer"]: build_player(game,modules,preset)
	if preset == "platformer":
		floor_node(game,Vector2(480,490),Vector2(960,48))
		floor_node(game,Vector2(440,355),Vector2(180,24),"Platform")
	var layer: CanvasLayer = CanvasLayer.new()
	layer.name = "Menus"
	layer.layer = 30
	game.add_child(layer)
	for kind: String in ["pause","over"]:
		var panel: Control = menu(config,kind,modules)
		layer.add_child(panel)
	var help: Label = Label.new()
	help.name = "ControlsHint"
	help.position = Vector2(20,16)
	help.text = "WASD／方向键移动 · Shift奔跑 · Space跳跃 · J攻击 · E交互 · Esc暂停 · F5／F9快速存取"
	layer.add_child(help)
	set_owners(game,game)
	error = save_scene(game,game_path)
	game.free()
	if not error.is_empty(): return {"error":error,"folder":folder}
	for row: Array in [["main","MainMenu"],["pause","PauseMenu"],["settings","SettingsMenu"],["save","SaveLoadMenu"],["over","GameOver"]]:
		var panel: Control = menu(config,str(row[0]),modules)
		set_owners(panel,panel)
		error = save_scene(panel,folder.path_join(str(row[1])+".tscn"))
		panel.free()
		if not error.is_empty(): return {"error":error,"folder":folder}
	# Game instances the saved menu scenes, so editing PauseMenu/GameOver files
	# immediately affects the game; no disconnected copies of these menus.
	var final_game: Node = (ResourceLoader.load(game_path,"PackedScene",ResourceLoader.CACHE_MODE_REPLACE) as PackedScene).instantiate()
	var menus: Node = final_game.get_node("Menus")
	for child: Node in menus.get_children():
		if child is Control and child.name in ["PauseMenu","GameOver"]: menus.remove_child(child); child.free()
	for path: String in [config["pause_scene"],config["over_scene"]]:
		var instance: Node = (load(path) as PackedScene).instantiate()
		menus.add_child(instance)
		instance.owner = final_game
	error = save_scene(final_game,game_path)
	final_game.free()
	if not error.is_empty(): return {"error":error,"folder":folder}
	var file: FileAccess = FileAccess.open(folder.path_join("Framework.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"version":1,"preset":preset,"framework":config},"\t"))
	file.close()
	if set_main:
		ProjectSettings.set_setting("application/run/main_scene",config["menu_scene"])
		var result: Error = ProjectSettings.save()
		if result != OK: return {"error":"模板已创建，但无法保存项目启动设置","folder":folder}
	return {"folder":folder,"scene":config["menu_scene"],"game":game_path,"config":config}


static func set_owners(parent: Node, root: Node) -> void:
	for child: Node in parent.get_children():
		child.owner = root
		set_owners(child,root)


static func save_scene(root: Node, path: String) -> String:
	var packed: PackedScene = PackedScene.new()
	if packed.pack(root) != OK or ResourceSaver.save(packed,path) != OK: return "无法保存场景："+path
	return ""


static func build_player(root: Node2D, modules: String, preset: String) -> void:
	var player: CharacterBody2D = CharacterBody2D.new()
	player.name = "Player"
	player.set_script(load(modules.path_join("framework_player.gd")))
	player.set("mode","platformer" if preset == "platformer" else "topdown")
	player.position = Vector2(160,360) if preset == "platformer" else Vector2(480,270)
	root.add_child(player)
	var visual: AnimatedSprite2D = AnimatedSprite2D.new()
	visual.name = "Visual"
	visual.sprite_frames = Assets.frames()
	visual.scale = Vector2(2,2)
	player.add_child(visual)
	var collision: CollisionShape2D = CollisionShape2D.new()
	var shape: CapsuleShape2D = CapsuleShape2D.new()
	shape.radius = 18
	shape.height = 56
	collision.shape = shape
	player.add_child(collision)


static func floor_node(root: Node2D, position: Vector2, dimensions: Vector2, name: String = "Ground") -> void:
	var body: StaticBody2D = StaticBody2D.new()
	body.name = name
	body.position = position
	root.add_child(body)
	var collision: CollisionShape2D = CollisionShape2D.new()
	var shape: RectangleShape2D = RectangleShape2D.new()
	shape.size = dimensions
	collision.shape = shape
	body.add_child(collision)
	var visual: Polygon2D = Polygon2D.new()
	visual.polygon = PackedVector2Array([-dimensions/2,Vector2(dimensions.x/2,-dimensions.y/2),dimensions/2,Vector2(-dimensions.x/2,dimensions.y/2)])
	visual.color = Color("37606a")
	body.add_child(visual)


static func menu(config: Dictionary, kind: String, modules: String) -> Control:
	var root: Control = Control.new()
	root.name = {"main":"MainMenu","pause":"PauseMenu","settings":"SettingsMenu","save":"SaveLoadMenu","over":"GameOver"}[kind]
	root.set_script(load(modules.path_join("framework_menu.gd")))
	root.set("framework",config.duplicate(true))
	root.set("menu_kind",kind)
	root.set("click_sound",Assets.sound("click"))
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var shade: ColorRect = ColorRect.new()
	shade.name = "Shade"
	shade.color = Color(0.04,0.08,0.13,0.92 if kind == "main" else 0.78)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(shade)
	var center: CenterContainer = CenterContainer.new()
	center.name = "Frame"
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(center)
	var panel: PanelContainer = PanelContainer.new()
	panel.custom_minimum_size = Vector2(420,0)
	center.add_child(panel)
	var margin: MarginContainer = MarginContainer.new()
	for edge: String in ["left","right","top","bottom"]: margin.add_theme_constant_override("margin_"+edge,24)
	panel.add_child(margin)
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(450 if kind == "settings" else 420,420)
	margin.add_child(scroll)
	var box: VBoxContainer = VBoxContainer.new()
	box.name = "Content"
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation",12)
	scroll.add_child(box)
	var title: Label = Label.new()
	title.name = "Title"
	title.text = {"main":"我的2D游戏","pause":"已暂停","settings":"设置","save":"存档与读取","over":"游戏结束"}[kind]
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size",28)
	box.add_child(title)
	var bindings: Dictionary = {}
	var actions: Array = {"main":[["StartButton","开始游戏","start"],["ContinueButton","继续游戏","continue"],["LoadButton","读取存档","load"],["SettingsButton","设置","settings"],["QuitButton","退出","quit"]],"pause":[["ResumeButton","继续游戏","resume"],["SaveButton","保存／读取","save"],["SettingsButton","设置","settings"],["RestartButton","重新开始","restart"],["MenuButton","返回主菜单","menu"]],"over":[["RestartButton","重新开始","restart"],["LoadButton","读取存档","load"],["MenuButton","返回主菜单","menu"]],"settings":[["ResetButton","恢复默认","reset"],["BackButton","返回","close"]],"save":[["BackButton","返回","close"]]}[kind]
	if kind == "settings":
		for channel: String in ["Master","BGM","SFX","UI"]:
			var caption: Label = Label.new()
			caption.text = channel+"音量／dB"
			box.add_child(caption)
			var slider: HSlider = HSlider.new()
			slider.name = channel+"Slider"
			slider.min_value = -60
			slider.max_value = 6
			box.add_child(slider)
		for entry: Array in [["WindowMode",["窗口","全屏","无边框"]],["Resolution",["960×540","1280×720","1920×1080"]]]:
			var options: OptionButton = OptionButton.new()
			options.name = entry[0]
			for text: String in entry[1]: options.add_item(text)
			box.add_child(options)
		for action: String in ["MoveLeft","MoveRight","MoveUp","MoveDown","Jump","Run","Attack","Interact","Pause","Inventory","Confirm","Cancel","QuickSave","QuickLoad"]:
			add_button(box,"Bind_"+action,action)
	if kind == "save":
		for slot: int in range(1,4):
			var caption: Label = Label.new()
			caption.name = "SlotTitle"+str(slot)
			box.add_child(caption)
			for operation: String in ["Save","Load","Delete"]:
				var id: String = operation+"Slot"+str(slot)
				add_button(box,id,{"Save":"保存","Load":"读取","Delete":"删除"}[operation]+" "+str(slot))
				bindings[id] = operation.to_lower()+":"+str(slot)
	for row: Array in actions:
		add_button(box,str(row[0]),str(row[1]))
		bindings[row[0]] = row[2]
	var status: Label = Label.new()
	status.name = "Status"
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.custom_minimum_size = Vector2(320,32)
	box.add_child(status)
	root.set("bindings",bindings)
	return root


static func add_button(parent: Node, name: String, caption: String) -> void:
	var button: Button = Button.new()
	button.name = name
	button.text = caption
	button.custom_minimum_size.y = 40
	parent.add_child(button)
