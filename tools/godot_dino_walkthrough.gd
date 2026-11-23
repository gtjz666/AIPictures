extends SceneTree
## Replays the manual tutorial in an isolated project with a private user:// directory.
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const MAIN: String = "res://Main.tscn"
const GAME: String = "res://DinoRun.tscn"
const PAUSE: String = "res://PauseMenu.tscn"
const SAVE: String = "res://SaveMenu.tscn"
const SETTINGS: String = "res://SettingsMenu.tscn"
const OVER: String = "res://GameOver.tscn"
const ART: String = "res://art/dino/ali_case"
const CLIPS: String = ART + "/DinoFrames.tres"
const FRAME_SIZE: int = 192
const SOUND: String = "res://audio/dino"
const AUDIO_CONTROLS: Dictionary = {"Master":"总音量", "BGM":"背景音乐", "SFX":"游戏音效", "UI":"界面音效"}
const ALIASES: Dictionary = {
	"tick":"物理帧", "velocity":"读取纵速", "gravity":"本帧重力", "sum":"新纵速", "write_velocity":"写入纵速", "move":"移动角色",
	"jump":"空格", "grounded":"检查落地", "can_jump":"能否跳跃", "launch":"写入起跳速度", "obstacle_x":"读取障碍X", "distance":"本帧距离",
	"next_x":"新障碍X", "write_x":"移动障碍", "outside":"比较边缘", "check_wrap":"是否出界", "wrap":"障碍回到右侧", "overlap":"碰撞",
	"pause":"暂停键", "show_pause":"打开暂停", "show_over":"打开结束", "init":"初始化", "loaded":"读档完成", "timer":"秒表",
	"number":"读取分数", "add_score":"分数加一", "store_score":"保存分数变量", "format":"格式化分数", "score":"更新分数界面",
	"screen":"画面比例", "play_run":"播放跑步", "play_jump":"播放跳跃", "play_death":"播放死亡", "motion_gate":"关卡运动闸门",
	"jump_gate":"跳跃输入闸门", "pause_gate":"暂停输入闸门", "end_once":"碰撞后只执行一次", "enter":"进入游戏", "load_slot":"读取槽位", "open_settings":"打开设置", "open_save":"打开存档",
	"home":"返回主界面", "close":"关闭当前界面", "store":"写入槽位", "show_note":"显示存档提示", "hide_note":"隐藏存档提示",
	"volume_down":"降低音量", "volume_normal":"还原音量", "reload":"重开跑酷"}
const GAME_POSITIONS: Dictionary = {
	"tick":[0,0], "velocity":[0,260], "gravity":[360,0], "sum":[730,0], "write_velocity":[1100,0], "move":[1460,0],
	"jump":[0,490], "grounded":[0,680], "can_jump":[390,490], "launch":[750,490], "play_jump":[1110,490], "play_run":[1470,490],
	"obstacle_x":[0,1050], "distance":[0,1310], "next_x":[370,1050], "outside":[370,1310], "write_x":[740,1050], "check_wrap":[1110,1050], "wrap":[1480,1050],
	"overlap":[0,1640], "end_once":[350,1640], "play_death":[720,1640], "show_over":[1100,1640], "motion_gate":[1460,1640],
	"pause":[0,1930], "pause_gate":[365,1930], "show_pause":[720,1930], "screen":[1100,1930], "jump_gate":[390,720],
	"init":[0,2220], "timer":[370,2220], "number":[0,2510], "add_score":[370,2510], "store_score":[740,2220], "format":[740,2510], "score":[1110,2220], "loaded":[1110,2510]}
var use_animation: bool = false
var use_audio: bool = false
var use_art: bool = false


func _initialize() -> void:
	if "--build" in OS.get_cmdline_user_args():
		make_case.call_deferred()
	elif "--check-settings-restart" in OS.get_cmdline_user_args():
		verify_settings_restart.call_deferred()
	else:
		verify.call_deferred()


func make_case() -> void:
	assert(build_animation_resource(), "生成素材必须先导入项目")
	use_audio = ResourceLoader.exists(SOUND + "/menu.wav")
	use_art = ResourceLoader.exists(ART + "/landscape.png")
	setup_case()
	print("DINO_PROJECT_READY")
	quit()


func build_animation_resource() -> bool:
	if not ResourceLoader.exists(ART + "/run.png"): return false
	var frames: SpriteFrames = SpriteFrames.new()
	frames.remove_animation("default")
	for clip: String in ["run", "jump", "death"]:
		var sheet: Texture2D = load(ART + "/" + clip + ".png") as Texture2D
		assert(sheet != null and sheet.get_size() == Vector2(8 * FRAME_SIZE, 6 * FRAME_SIZE))
		frames.add_animation(clip)
		frames.set_animation_speed(clip, 24)
		frames.set_animation_loop(clip, clip == "run")
		for index: int in range(48):
			var cell: AtlasTexture = AtlasTexture.new()
			cell.atlas = sheet
			cell.region = Rect2((index % 8) * FRAME_SIZE, floori(index / 8.0) * FRAME_SIZE, FRAME_SIZE, FRAME_SIZE)
			cell.filter_clip = true
			frames.add_frame(clip, cell)
	use_animation = ResourceSaver.save(frames, CLIPS) == OK
	return use_animation


func build(path: String, title: String, buttons: Array, nodes: Array, wires: Array, note: bool = false, game_hud: bool = false) -> void:
	var host: Node2D = Node2D.new()
	host.name = path.get_file().get_basename()
	var runtime: Node2D = Builder.new_runtime()
	host.add_child(runtime)
	runtime.owner = host
	var data: Dictionary = Model.empty_scene(path)
	if path == GAME and use_animation: add_animation_wires(nodes, wires)
	if path == SETTINGS: add_audio_settings(nodes, wires)
	if use_audio: add_audio_wires(path, nodes, wires)
	var event_index: int = 0
	var operation_index: int = 0
	for row: Array in nodes:
		var pos: Array = GAME_POSITIONS.get(row[0], [1850,operation_index * 220])
		if path != GAME:
			if row[1] == "ui_event":
				pos = [0, event_index * 185]
				event_index += 1
			else:
				pos = [400, operation_index * 185]
				operation_index += 1
		elif not GAME_POSITIONS.has(row[0]):
			operation_index += 1
		var node: Dictionary = Model.module(row[0],row[1],float(pos[0]),float(pos[1]))
		node["title"] = str(row[3]) if row.size() > 3 else ALIASES.get(row[0], str(row[2].get("target", "")) + " 交互事件" if row[1] == "ui_event" else Model.TITLES[row[1]])
		node["params"].merge(row[2],true)
		data["nodes"].append(node)
	for edge: Array in wires:
		data["edges"].append({"from":edge[0],"from_port":edge[1],"to":edge[2],"to_port":edge[3]})
	var issue: String = Model.validate(data)
	assert(issue.is_empty(),path+" "+issue)
	runtime.set("game_blueprint", data)
	if use_art: add_scene_art(host,path)
	if not title.is_empty():
		var heading: Label = label(host,"Title",title,Vector2(32,27))
		heading.add_theme_font_size_override("font_size", 25)
	for i: int in range(buttons.size()):
		var btn: Button = Button.new()
		btn.name = buttons[i][0]
		btn.text = buttons[i][1]
		btn.position = Vector2(32, (360 if path == SETTINGS else 90) + i * 51)
		btn.size = Vector2(220, 40)
		host.add_child(btn)
		btn.owner = host
		if use_art: style_button(btn)
	if path == SETTINGS: create_audio_controls(host)
	if note: label(host,"Note","存档已写入",Vector2(32,264)).hide()
	if game_hud: create_game_objects(host)
	var packed: PackedScene = PackedScene.new()
	assert(packed.pack(host) == OK)
	assert(ResourceSaver.save(packed,path) == OK)
	host.free()


func add_audio_settings(nodes: Array, wires: Array) -> void:
	nodes.append_array([["settings_init","game_event",{"event":"initialized"},"设置初始化"],
		["read_settings","settings_service",{"operation":"read"},"读取当前设置"],
		["restore_default","settings_service",{"operation":"reset_audio"},"恢复默认音量"],
		["volume_table","collection",{"key":"volumes","value_type":"dictionary"},"读取四路音量"]])
	wires.append_array([["settings_init",0,"read_settings",0],["reset",0,"restore_default",0],
		["restore_default",0,"read_settings",0],["read_settings",3,"volume_table",0]])
	for channel: String in AUDIO_CONTROLS:
		var suffix: String = channel.to_lower()
		var label_text: String = AUDIO_CONTROLS[channel]
		var control: String = channel + "Volume"
		var read: String = "read_" + suffix
		var sync: String = "sync_" + suffix
		var changed: String = "change_" + suffix
		var write: String = "write_" + suffix
		nodes.append_array([[read,"collection",{"key":channel,"value_type":"number"},"读取" + label_text],
			[sync,"ui_control",{"target":control,"operation":"value_quiet","value_type":"number"},"同步" + label_text + "滑条"],
			[changed,"ui_event",{"target":control,"signal":"value_changed","value_type":"number"},label_text + "滑动"],
			[write,"settings_service",{"operation":"volume","channel":channel},"保存" + label_text]])
		wires.append_array([["volume_table",0,read,0],[read,0,sync,1],["read_settings",0,sync,0],
			[changed,0,write,0],[changed,1,write,1]])


func create_audio_controls(host: Node2D) -> void:
	var hint: Label = label(host,"AudioHint","左端为静音，向右调高音量。修改后自动保存。",Vector2(32,70))
	hint.size.x = 465
	hint.modulate = Color("cee3d3")
	var row: int = 0
	for channel: String in AUDIO_CONTROLS:
		var y: float = 119.0 + row * 55.0
		var name_label: Label = label(host,channel + "Label",AUDIO_CONTROLS[channel],Vector2(32,y))
		name_label.size = Vector2(105,32)
		var slider: HSlider = HSlider.new()
		slider.name = channel + "Volume"
		slider.position = Vector2(150,y + 9)
		slider.size = Vector2(285,24)
		slider.min_value = -60
		slider.max_value = 0
		slider.step = 1
		slider.value = float(Model.params("mixer")[channel])
		slider.tooltip_text = AUDIO_CONTROLS[channel] + "（最左为静音）"
		host.add_child(slider)
		slider.owner = host
		row += 1


func sound_node(id: String, file: String, channel: String, caption: String, loops: bool = false) -> Array:
	return [id,"audio_fx",{"path":SOUND + "/" + file + ".wav","channel":channel,"loop":loops,"persist_ui":channel == "UI"},caption]


func add_audio_wires(path: String, nodes: Array, wires: Array) -> void:
	if path == GAME:
		nodes.append_array([sound_node("level_music","level","BGM","关卡音乐",true),
			sound_node("jump_sound","jump","SFX","跳跃音效"),
			sound_node("death_sound","death","SFX","死亡音效"),
			sound_node("menu_click","click","UI","暂停交互音效")])
		var impact: String = "end_once" if use_animation else "overlap"
		var pause_trigger: String = "pause_gate" if use_animation else "pause"
		wires.append_array([["init",0,"level_music",0],["launch",0,"jump_sound",0],
			[impact,0,"level_music",1],[impact,0,"death_sound",0],[pause_trigger,0,"menu_click",0]])
		return
	if path == MAIN:
		nodes.append_array([["main_init","game_event",{"event":"initialized"},"菜单初始化"],
			sound_node("menu_music","menu","BGM","主菜单音乐",true)])
		wires.append(["main_init",0,"menu_music",0])
	nodes.append(sound_node("menu_click","click","UI","按钮交互音效"))
	for row: Array in nodes:
		if row[1] == "ui_event" and row[2].get("signal","pressed") == "pressed":
			wires.append([row[0],0,"menu_click",0])


func add_animation_wires(nodes: Array, wires: Array) -> void:
	for id: String in ["run", "jump", "death"]:
		nodes.append(["play_" + id, "animation", {"target":"Player/Visual", "mode":"frames", "frames":CLIPS, "clip":id, "loops":0 if id == "run" else 1, "wait":id != "run", "speed":2.45 if id == "jump" else 1.0}])
	for gate: String in ["motion_gate", "jump_gate", "pause_gate"]: nodes.append([gate, "gate", {}])
	nodes.append(["end_once", "do_once", {}])
	wires.erase(["overlap",0,"show_over",0])
	wires.erase(["tick",0,"write_velocity",0])
	wires.erase(["tick",0,"write_x",0])
	wires.erase(["jump",0,"can_jump",0])
	wires.erase(["pause",0,"show_pause",0])
	wires.append_array([["jump",0,"jump_gate",0],["jump_gate",0,"can_jump",0],["pause",0,"pause_gate",0],["pause_gate",0,"show_pause",0],
		["tick",0,"motion_gate",0],["motion_gate",0,"write_velocity",0],["motion_gate",0,"write_x",0],
		["init",0,"play_run",0],["launch",0,"play_jump",0],["play_jump",0,"play_run",0],
		["overlap",0,"end_once",0],["end_once",0,"motion_gate",2],["end_once",0,"jump_gate",2],["end_once",0,"pause_gate",2],["end_once",0,"timer",1],
		["end_once",0,"play_death",0],["play_death",0,"show_over",0]])


func panel_style(tint: Color = Color.WHITE) -> StyleBoxTexture:
	var style: StyleBoxTexture = StyleBoxTexture.new()
	style.texture = load(ART + "/panel.png") as Texture2D
	style.modulate_color = tint
	for side: int in [SIDE_LEFT,SIDE_TOP,SIDE_RIGHT,SIDE_BOTTOM]:
		style.set_texture_margin(side,12)
	return style


func style_button(button: Button) -> void:
	button.add_theme_stylebox_override("normal",panel_style(Color("91cfbc")))
	button.add_theme_stylebox_override("hover",panel_style(Color("d2ffdc")))
	button.add_theme_stylebox_override("pressed",panel_style(Color("75a792")))
	var focus: StyleBoxFlat = StyleBoxFlat.new()
	focus.draw_center = false
	focus.border_color = Color("fff4b3")
	focus.set_border_width_all(2)
	button.add_theme_stylebox_override("focus",focus)
	button.add_theme_font_size_override("font_size",18)
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND


func add_panel(host: Node2D, name: String, origin: Vector2, dimensions: Vector2) -> void:
	var panel: Panel = Panel.new()
	panel.name = name
	panel.position = origin
	panel.size = dimensions
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	panel.add_theme_stylebox_override("panel",panel_style())
	host.add_child(panel)
	panel.owner = host


func add_scene_art(host: Node2D, path: String) -> void:
	if path in [MAIN,GAME]:
		var layer: CanvasLayer = CanvasLayer.new()
		layer.name = "Backdrop"
		layer.layer = -1
		host.add_child(layer)
		layer.owner = host
		var background: TextureRect = TextureRect.new()
		background.name = "Landscape"
		background.texture = load(ART + "/landscape.png") as Texture2D
		background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		background.mouse_filter = Control.MOUSE_FILTER_IGNORE
		background.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		layer.add_child(background)
		background.owner = host
		background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	if path == GAME:
		add_panel(host,"ScorePlate",Vector2(8,6),Vector2(173,49))
		return
	var height: float = 468 if path == SETTINGS else 320 if path in [PAUSE,SAVE] else 280 if path == MAIN else 220
	add_panel(host,"MenuPlate",Vector2(12,12),Vector2(455 if path == SETTINGS else 264,height))
	if path == MAIN and use_animation:
		var mascot: AnimatedSprite2D = AnimatedSprite2D.new()
		mascot.name = "DinoPreview"
		mascot.sprite_frames = load(CLIPS) as SpriteFrames
		mascot.autoplay = "run"
		mascot.position = Vector2(584,302)
		mascot.scale = Vector2(1.85,1.85)
		mascot.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		host.add_child(mascot)
		mascot.owner = host


func create_game_objects(host: Node2D) -> void:
	label(host,"Score","分数 0",Vector2(20,16))
	var floor: StaticBody2D = StaticBody2D.new()
	floor.name = "Floor"
	floor.position = Vector2(480,454)
	floor.collision_layer = 2
	floor.collision_mask = 0
	add_shape(host, floor, Vector2(960,40))
	if use_art:
		var strip: TextureRect = TextureRect.new()
		strip.name = "Grass"
		strip.position = Vector2(-480,-20)
		strip.size = Vector2(960,40)
		strip.texture = load(ART + "/ground.png") as Texture2D
		strip.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		strip.stretch_mode = TextureRect.STRETCH_TILE
		strip.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		strip.mouse_filter = Control.MOUSE_FILTER_IGNORE
		floor.add_child(strip)
		strip.owner = host
	else:
		add_swatch(host,floor,Vector2(960,40),Color("335c5f"))
	var player: CharacterBody2D = CharacterBody2D.new()
	player.name = "Player"
	player.position = Vector2(100,414)
	player.collision_mask = 2
	add_shape(host, player, Vector2(32,40))
	if use_animation:
		var visual: AnimatedSprite2D = AnimatedSprite2D.new()
		visual.name = "Visual"
		visual.position = Vector2(-54,-77)
		visual.scale = Vector2(0.5625,0.5625)
		visual.centered = false
		visual.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		visual.sprite_frames = load(CLIPS) as SpriteFrames
		visual.animation = &"run"
		player.add_child(visual)
		visual.owner = host
	else:
		add_swatch(host,player,Vector2(32,40),Color("80b777"))
	var obstacle: Area2D = Area2D.new()
	obstacle.name = "Obstacle"
	obstacle.position = Vector2(980,410)
	add_shape(host, obstacle, Vector2(30,48))
	if use_art:
		var cactus: Sprite2D = Sprite2D.new()
		cactus.name = "Cactus"
		cactus.texture = load(ART + "/cactus.png") as Texture2D
		cactus.scale = Vector2(37,48) / cactus.texture.get_size()
		cactus.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		obstacle.add_child(cactus)
		cactus.owner = host
	else:
		add_swatch(host,obstacle,Vector2(30,48),Color("bd6949"))


func add_swatch(host: Node2D, body: Node2D, size: Vector2, shade: Color) -> void:
	var swatch: ColorRect = ColorRect.new()
	swatch.name = "ColorRect"
	swatch.position = -size / 2.0
	swatch.size = size
	swatch.color = shade
	swatch.mouse_filter = Control.MOUSE_FILTER_IGNORE
	body.add_child(swatch)
	swatch.owner = host


func add_shape(host: Node2D, body: CollisionObject2D, size: Vector2) -> void:
	host.add_child(body)
	body.owner = host
	var hitbox: CollisionShape2D = CollisionShape2D.new()
	var rect: RectangleShape2D = RectangleShape2D.new()
	rect.size = size
	hitbox.shape = rect
	body.add_child(hitbox)
	hitbox.owner = host


func label(host: Node2D, id: String, caption: String, pos: Vector2) -> Label:
	var control: Label = Label.new()
	control.name = id
	control.text = caption
	control.position = pos
	control.size = Vector2(220,40)
	host.add_child(control)
	control.owner = host
	return control


func button_event(id: String, target: String) -> Array:
	return [id,"ui_event",{"target":target}]


func scene_node(id: String, operation: String, path: String = "", pause: bool = false) -> Array:
	return [id,"scene_service",{"operation":operation,"scene":path,"pause_world":pause,"fade":0.1}]


func setup_case() -> void:
	build(MAIN,"小恐龙跑酷",[["Start","开始游戏"],["Load","读取存档"],["Settings","设置"]],
		[button_event("start","Start"),button_event("load_game","Load"),button_event("settings","Settings"),scene_node("enter","change",GAME),
		 ["load_slot","save_service",{"operation":"load","slot":1}],scene_node("open_settings","open_overlay",SETTINGS)],
		[["start",0,"enter",0],["load_game",0,"load_slot",0],["settings",0,"open_settings",0]])
	build(GAME,"",[],[
		["tick","frame_event",{}],["screen","screen",{}],
		["velocity","property_get",{"target":"Player","property":"velocity:y","value_type":"number"}],
		["gravity","math",{"op":"multiply","a":1600.0}],["sum","math",{"op":"add"}],
		["write_velocity","property_set",{"target":"Player","property":"velocity:y","value_type":"number","json":"0"}],
		["move","method_call",{"target":"Player","method":"move_and_slide"}],
		["jump","key_event",{"key":KEY_SPACE}],["grounded","body_contact",{"target":"Player","surface":"floor"}],["can_jump","branch",{}],
		["launch","property_set",{"target":"Player","property":"velocity:y","value_type":"number","json":"-620"}],
		["obstacle_x","property_get",{"target":"Obstacle","property":"position:x","value_type":"number"}],
		["distance","math",{"op":"multiply","a":300.0}],["next_x","math",{"op":"subtract"}],
		["write_x","property_set",{"target":"Obstacle","property":"position:x","value_type":"number","json":"980"}],
		["outside","compare",{"op":"less_equal","b":-30.0}],["check_wrap","branch",{}],
		["wrap","property_set",{"target":"Obstacle","property":"position:x","value_type":"number","json":"980"}],
		["overlap","signal_event",{"target":"Obstacle","signal":"body_entered"}],
		["pause","key_event",{"key":KEY_ESCAPE}],scene_node("show_pause","open_overlay",PAUSE,true),scene_node("show_over","open_overlay",OVER,true),
		["init","game_event",{"event":"initialized"}],["loaded","game_event",{"event":"loaded"}],["timer","timer",{}],
		["number","blackboard",{"name":"score"}],["add_score","math",{"op":"add","b":1.0}],
		["store_score","set_variable",{"name":"score"}],["format","format_text",{"template":"分数 {value}"}],
		["score","ui_control",{"target":"Score","operation":"text","value_type":"text"}]],
		[["tick",1,"gravity",1],["velocity",0,"sum",0],["gravity",0,"sum",1],["sum",0,"write_velocity",1],
		 ["tick",0,"write_velocity",0],["write_velocity",0,"move",0],["jump",0,"can_jump",0],["grounded",0,"can_jump",1],["can_jump",0,"launch",0],
		 ["tick",1,"distance",1],["obstacle_x",0,"next_x",0],["distance",0,"next_x",1],["next_x",0,"write_x",1],["tick",0,"write_x",0],
		 ["obstacle_x",0,"outside",0],["outside",0,"check_wrap",1],["write_x",0,"check_wrap",0],["check_wrap",0,"wrap",0],
		 ["overlap",0,"show_over",0],["pause",0,"show_pause",0],
		 ["init",0,"timer",0],["timer",0,"store_score",0],["number",0,"add_score",0],["add_score",0,"store_score",1],
		 ["store_score",0,"score",0],["loaded",0,"score",0],["number",0,"format",0],["format",0,"score",1]],false,true)
	build(PAUSE,"已暂停",[["Resume","继续游戏"],["Save","存档与读取"],["Settings","设置"],["Menu","返回主界面"]],
		[button_event("resume","Resume"),button_event("save","Save"),button_event("settings","Settings"),button_event("menu","Menu"),
		 scene_node("close","close_overlay"),scene_node("open_save","open_overlay",SAVE),scene_node("open_settings","open_overlay",SETTINGS),scene_node("home","change",MAIN)],
		[["resume",0,"close",0],["save",0,"open_save",0],["settings",0,"open_settings",0],["menu",0,"home",0]])
	build(SAVE,"存档与读取",[["Write","保存到槽位 1"],["Load","读取槽位 1"],["Back","返回暂停"]],
		[button_event("write","Write"),button_event("read","Load"),button_event("back","Back"),
		 ["store","save_service",{"operation":"save","slot":1}],["load_slot","save_service",{"operation":"load","slot":1}],
		 ["show_note","ui_control",{"target":"Note","operation":"show"}],
		 ["hide_note","ui_control",{"target":"Note","operation":"hide"}],scene_node("close","close_overlay")],
		[["write",0,"store",0],["store",0,"show_note",0],["read",0,"load_slot",0],["back",0,"hide_note",0],["hide_note",0,"close",0]],true)
	build(SETTINGS,"声音设置",[["Reset","恢复默认音量"],["Back","返回"]],
		[button_event("reset","Reset"),button_event("back","Back"),scene_node("close","close_overlay")],
		[["back",0,"close",0]])
	build(OVER,"游戏结束",[["Retry","再来一局"],["Menu","返回主界面"]],
		[button_event("retry","Retry"),button_event("menu","Menu"),scene_node("reload","reload"),scene_node("home","change",MAIN)],
		[["retry",0,"reload",0],["menu",0,"home",0]])


func frames(n: int = 4) -> void:
	for i: int in range(n): await process_frame


func press(panel: Node, button_name: String) -> void:
	var button: Button = panel.get_node(NodePath(button_name)) as Button
	assert(button != null and button.can_process())
	button.pressed.emit()


func top(manager: Node, path: String) -> Node:
	var layers: Array = manager.get("overlays")
	assert(not layers.is_empty() and layers.back()["path"] == path,str(layers))
	return layers.back()["panel"] as Node


func key(game: Node, code: int) -> void:
	var event: InputEventKey = InputEventKey.new()
	event.pressed = true
	event.keycode = code
	game.call("_unhandled_key_input",event)


func until_scene(path: String) -> void:
	var deadline: int = Time.get_ticks_msec() + 12000
	while Time.get_ticks_msec() < deadline:
		if current_scene != null and current_scene.scene_file_path == path:
			await frames(6)
			return
		await process_frame
	push_error("未切换到 "+path)
	quit(1)


func sound_voice(game: Node, id: String) -> AudioStreamPlayer:
	var voice: AudioStreamPlayer = game.get("audio_tools").get("voices").get(id) as AudioStreamPlayer
	assert(voice != null and voice.stream != null, id)
	return voice


func volume_slider(panel: Node, channel: String) -> HSlider:
	return panel.get_node(channel + "Volume") as HSlider


func verify_settings_restart() -> void:
	assert(change_scene_to_file(MAIN) == OK)
	await until_scene(MAIN)
	var runtime: Node = Builder.scene_runtime(current_scene)
	var service: Node = runtime.get("services")
	var expected: Dictionary = {"Master":-20.0,"BGM":-18.0,"SFX":-10.0,"UI":-6.0}
	assert(service.get("settings")["volumes"] == expected)
	assert(runtime.get("mixer_values") == expected)
	press(current_scene,"Settings")
	await frames()
	var settings_panel: Node = top(service.get("scenes"),SETTINGS)
	for channel: String in expected:
		assert(volume_slider(settings_panel,channel).value == float(expected[channel]))
	print("DINO_AUDIO_SETTINGS_RESTART_PASS")
	quit()


func verify() -> void:
	if "--check-built" in OS.get_cmdline_user_args():
		use_animation = true
		use_audio = ResourceLoader.exists(SOUND + "/menu.wav")
		use_art = ResourceLoader.exists(ART + "/landscape.png")
		var art: SpriteFrames = load(CLIPS) as SpriteFrames
		for clip: String in ["run", "jump", "death"]:
			assert(art.get_frame_count(clip) == 48 and art.get_animation_speed(clip) == 24)
	else:
		setup_case()
	assert(change_scene_to_file(MAIN) == OK)
	await until_scene(MAIN)
	var main: Node = Builder.scene_runtime(current_scene)
	var service: Node = main.get("services")
	var manager: Node = service.get("scenes")
	if use_art:
		var title_backdrop: TextureRect = current_scene.get_node("Backdrop/Landscape") as TextureRect
		assert(title_backdrop.texture != null and current_scene.has_node("MenuPlate"))
		assert(title_backdrop.get_rect().encloses(get_root().get_visible_rect()))
	var main_music: AudioStreamPlayer
	if use_audio:
		main_music = sound_voice(main,"menu_music")
		var stream: AudioStreamWAV = main_music.stream as AudioStreamWAV
		assert(main_music.playing and stream.loop_mode == AudioStreamWAV.LOOP_FORWARD and stream.loop_end > stream.loop_begin)
	press(current_scene,"Settings")
	await frames()
	var settings: Node = top(manager,SETTINGS)
	assert(not paused and service.call("current_game") == main)
	if use_audio: assert(main_music.playing and not main_music.stream_paused and service.get("interface_voice") != null)
	if use_art: assert(settings.has_node("MenuPlate"))
	for channel: String in AUDIO_CONTROLS:
		assert(is_equal_approx(volume_slider(settings, channel).value, float(service.get("settings")["volumes"][channel])))
	volume_slider(settings,"BGM").value = -60.0
	assert(AudioServer.is_bus_mute(AudioServer.get_bus_index(main.get("bus_names")["BGM"])))
	press(settings,"Reset")
	assert(volume_slider(settings,"BGM").value == -12.0)
	volume_slider(settings,"Master").value = -20.0
	volume_slider(settings,"BGM").value = -18.0
	volume_slider(settings,"SFX").value = -10.0
	volume_slider(settings,"UI").value = -6.0
	assert(service.get("storage").call("read_settings")["volumes"]["Master"] == -20.0)
	press(settings,"Back")
	await frames()
	assert(not paused and manager.get("overlays").is_empty())
	if use_audio:
		var click: AudioStreamPlayer = service.get("interface_voice") as AudioStreamPlayer
		assert(click.is_inside_tree() and click.stream != null and click.volume_db == -26.0)
	press(current_scene,"Start")
	await until_scene(GAME)
	var game: Node = Builder.scene_runtime(current_scene)
	assert(game.get("state") == "running" and game.get("mixer_values")["Master"] == -20.0)
	assert(game.get("mixer_values")["BGM"] == -18.0 and game.get("mixer_values")["SFX"] == -10.0)
	var level_music: AudioStreamPlayer
	if use_audio:
		assert(not is_instance_valid(main_music))
		level_music = sound_voice(game,"level_music")
		assert(level_music.playing and not level_music.stream_paused)
	if use_art:
		var backdrop: TextureRect = current_scene.get_node("Backdrop/Landscape") as TextureRect
		assert(backdrop.texture != null and backdrop.get_rect().encloses(get_root().get_visible_rect()))
		assert(current_scene.get_node("Floor/Grass").texture != null and current_scene.get_node("Obstacle/Cactus").texture != null)
	await frames(12)
	var player: CharacterBody2D = current_scene.get_node("Player") as CharacterBody2D
	var obstacle: Area2D = current_scene.get_node("Obstacle") as Area2D
	assert(player.is_on_floor())
	assert(obstacle.position.x < 980.0)
	key(game,KEY_SPACE)
	await frames(3)
	assert(player.velocity.y < 0.0 and player.position.y < 414.0)
	if use_animation: assert(player.get_node("Visual").animation == &"jump")
	if use_audio: assert(sound_voice(game,"jump_sound").bus == game.get("bus_names")["SFX"])
	await frames(65)
	assert(game.get("variables")["score"] > 0 and str(current_scene.get_node("Score").text).begins_with("分数 "))
	key(game,KEY_ESCAPE)
	await frames()
	var pause_menu: Node = top(manager,PAUSE)
	assert(paused and game.get("state") == "paused")
	if use_audio: assert(level_music.stream_paused)
	var elapsed: float = game.get("elapsed")
	var score: float = game.get("variables")["score"]
	press(pause_menu,"Settings")
	await frames()
	settings = top(manager,SETTINGS)
	assert(volume_slider(settings,"SFX").value == -10.0)
	volume_slider(settings,"UI").value = -60.0
	assert(service.get("settings")["volumes"]["UI"] == -60.0 and paused)
	if use_audio: assert(not service.get("interface_voice").playing)
	volume_slider(settings,"UI").value = -6.0
	press(settings,"Back")
	await frames()
	assert(paused and top(manager,PAUSE) == pause_menu)
	press(pause_menu,"Save")
	await frames()
	var save_menu: Node = top(manager,SAVE)
	assert(not save_menu.get_node("Note").visible and service.call("current_game") == game)
	press(save_menu,"Write")
	await frames()
	assert(save_menu.get_node("Note").visible)
	var saved: Dictionary = service.get("storage").call("read",1)
	assert(not saved.has("error") and saved["data"]["scene"] == GAME,str(saved))
	assert(saved["data"]["variables"]["score"] == score)
	press(save_menu,"Back")
	assert(not save_menu.get_node("Note").visible)
	await frames()
	assert(paused and game.get("elapsed") == elapsed)
	assert(top(manager,PAUSE) == pause_menu and pause_menu.get_parent().visible)
	press(pause_menu,"Resume")
	await frames()
	assert(not paused and game.get("state") == "running" and manager.get("overlays").is_empty())
	if use_audio: assert(level_music.playing and not level_music.stream_paused)
	key(game,KEY_ESCAPE)
	await frames()
	press(top(manager,PAUSE),"Menu")
	await until_scene(MAIN)
	assert(not paused and manager.get("overlays").is_empty())
	press(current_scene,"Load")
	await until_scene(GAME)
	await frames(12)
	game = Builder.scene_runtime(current_scene)
	assert(not paused and game.get("state") == "running" and game.get("variables")["score"] >= score)
	player = current_scene.get_node("Player") as CharacterBody2D
	obstacle = current_scene.get_node("Obstacle") as Area2D
	obstacle.position.x = -29.0
	await frames(4)
	assert(obstacle.position.x > 900.0)
	obstacle.position = player.position + Vector2(50,0)
	await frames(18)
	if use_audio:
		assert(not sound_voice(game,"level_music").playing)
		assert(sound_voice(game,"death_sound").bus == game.get("bus_names")["SFX"])
	if use_animation:
		assert(player.get_node("Visual").animation == &"death" and not paused)
		key(game,KEY_SPACE)
		key(game,KEY_ESCAPE)
		await frames(4)
		assert(player.get_node("Visual").animation == &"death" and not paused)
		await frames(125)
	else:
		await frames(7)
	assert(paused and game.get("state") == "paused")
	press(top(manager,OVER),"Retry")
	if current_scene != null: await scene_changed
	await frames(15)
	assert(current_scene.scene_file_path == GAME and Builder.scene_runtime(current_scene).get("state") == "running")
	assert(manager.get("overlays").is_empty())
	if use_animation: assert(current_scene.get_node("Player/Visual").animation == &"run")
	if use_audio: assert(sound_voice(Builder.scene_runtime(current_scene),"level_music").playing)
	var transition: RefCounted = manager.get("active")
	if transition != null and transition.get("state") == "running": await transition.settled
	assert(transition != null and transition.get("state") == "completed")
	await create_timer(0.2).timeout
	print("DINO_WALKTHROUGH_PASS main / gameplay / pause / save / settings / game over")
	quit()
