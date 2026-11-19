@tool
extends EditorPlugin

const DragAsset: GDScript = preload("asset_drag.gd")
const BlueprintWindow: GDScript = preload("blueprint_window.gd")
const GameWindow: GDScript = preload("game_window.gd")
const FrameworkWizard: GDScript = preload("framework_wizard.gd")
const Builder: GDScript = preload("game_builder.gd")
const Model: GDScript = preload("game_model.gd")
const Access: GDScript = preload("blueprint_access.gd")
const ASSET_FOLDERS: Array[String] = ["art/dino", "art/world", "art/ui", "audio", "generated/ali_assets"]
var dock: VBoxContainer
var application: LineEdit
var kind: OptionButton
var assets: VBoxContainer
var status: Label
var refresh_timer: Timer
var chooser: FileDialog
var known_catalog: PackedStringArray = []
var catalog_initialized: bool = false
var blueprint: Window
var game_window: Window
var framework_wizard: Window



func _enter_tree() -> void:
	add_to_group("ali_assets_editor")
	dock = VBoxContainer.new()
	dock.name = "AlI 素材"
	dock.custom_minimum_size.x = 240
	var edit_scene: Button = Button.new()
	edit_scene.text = "场景蓝图…"
	edit_scene.pressed.connect(open_game_window)
	dock.add_child(edit_scene)
	var create_scene: Button = Button.new()
	create_scene.text = "新建蓝图场景…"
	create_scene.pressed.connect(func() -> void:
		open_game_window()
		game_window.call("choose","new_canvas"))
	dock.add_child(create_scene)
	scene_changed.connect(sync_scene)
	var settings: CheckButton = CheckButton.new()
	settings.text = "生成器设置"
	dock.add_child(settings)
	var generator_settings: VBoxContainer = VBoxContainer.new()
	generator_settings.hide()
	dock.add_child(generator_settings)
	settings.toggled.connect(func(shown: bool) -> void: generator_settings.visible = shown)
	application = LineEdit.new()
	application.placeholder_text = "AlI 软件文件夹"
	generator_settings.add_child(application)
	var config: Variant = JSON.parse_string(FileAccess.get_file_as_string(get_script().resource_path.get_base_dir().path_join("application.json"))) if FileAccess.file_exists(get_script().resource_path.get_base_dir().path_join("application.json")) else null
	if config is Dictionary:
		application.text = str(config.get("root", ""))
	var remembered: String = str(EditorInterface.get_editor_settings().get_project_metadata("ali_assets", "application_root", ""))
	if not remembered.is_empty():
		application.text = remembered
	var browse: Button = Button.new()
	browse.text = "选择软件目录…"
	generator_settings.add_child(browse)
	chooser = FileDialog.new()
	chooser.access = FileDialog.ACCESS_FILESYSTEM
	chooser.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	dock.add_child(chooser)
	browse.pressed.connect(func() -> void: chooser.popup_centered_ratio(0.7))
	chooser.dir_selected.connect(func(path: String) -> void:
		application.text = path
		EditorInterface.get_editor_settings().set_project_metadata("ali_assets", "application_root", path))
	kind = OptionButton.new()
	for title: String in ["图片", "精灵动画", "游戏音效", "背景配乐"]:
		kind.add_item(title)
	dock.add_child(kind)
	var open_button: Button = Button.new()
	open_button.text = "打开生成窗口"
	open_button.pressed.connect(open_generator)
	dock.add_child(open_button)
	var examples: MenuButton = MenuButton.new()
	examples.text = "示例模板"
	examples.get_popup().add_item("创建旧版 2D 游戏框架…",0)
	examples.get_popup().id_pressed.connect(func(_id: int) -> void:
		if not is_instance_valid(framework_wizard): framework_wizard = FrameworkWizard.new(); dock.add_child(framework_wizard)
		framework_wizard.popup_centered())
	dock.add_child(examples)
	set_process_input(true)
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	dock.add_child(status)
	var refresh: Button = Button.new()
	refresh.text = "刷新已导出组件"
	refresh.pressed.connect(refresh_assets)
	dock.add_child(refresh)
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	assets = VBoxContainer.new()
	assets.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(assets)
	dock.add_child(scroll)
	refresh_timer = Timer.new()
	refresh_timer.wait_time = 3.0
	refresh_timer.timeout.connect(refresh_assets)
	dock.add_child(refresh_timer)
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, dock)
	refresh_timer.start()
	prepare_asset_folders()
	refresh_assets.call_deferred()


func prepare_asset_folders() -> void:
	var project: DirAccess = DirAccess.open("res://")
	if project == null:
		status.text = "无法打开项目目录，素材文件夹未创建。"
		return
	var created: bool = false
	var unavailable: PackedStringArray = []
	for path: String in ASSET_FOLDERS:
		if project.dir_exists(path):
			continue
		var parent: String = path.get_base_dir()
		if project.is_link(path) or (not parent.is_empty() and project.is_link(parent)):
			unavailable.append(path)
			continue
		if project.make_dir_recursive(path) == OK:
			created = true
		else:
			unavailable.append(path)
	if not unavailable.is_empty():
		status.text = "无法创建素材文件夹：" + ", ".join(unavailable)
	if created:
		var filesystem: EditorFileSystem = EditorInterface.get_resource_filesystem()
		if not filesystem.is_scanning():
			filesystem.scan.call_deferred()


func open_generator() -> void:
	var root: String = application.text.strip_edges().replace("\\", "/")
	var executable: String = root.path_join(".venv/Scripts/pythonw.exe") if OS.get_name() == "Windows" else root.path_join(".venv/bin/python")
	if not FileAccess.file_exists(executable):
		executable = root.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(executable) or not FileAccess.file_exists(root.path_join("aipictures/app.py")):
		status.text = "请选择已安装运行环境的AlI软件目录。"
		return
	var kinds: PackedStringArray = ["image", "animation", "sfx", "music"]
	var arguments: PackedStringArray = [root.path_join("launch_godot.py"), "--godot-project", ProjectSettings.globalize_path("res://"), "--asset-kind", kinds[kind.selected]]
	var pid: int = OS.create_process(executable, arguments, false)
	status.text = "已打开独立生成窗口。" if pid > 0 else "窗口启动失败，请检查软件路径。"


func refresh_assets() -> void:
	var directory: DirAccess = DirAccess.open("res://".path_join("generated/ali_assets"))
	if directory == null:
		return
	var catalog: PackedStringArray = []
	for folder: String in directory.get_directories():
		if FileAccess.file_exists("res://generated/ali_assets/" + folder + "/asset.json"):
			catalog.append(folder)
	catalog.sort()
	if catalog_initialized and known_catalog == catalog:
		return
	if catalog_initialized:
		var filesystem: EditorFileSystem = EditorInterface.get_resource_filesystem()
		if filesystem.is_scanning():
			return
		filesystem.scan()
	known_catalog = catalog
	catalog_initialized = true
	for child: Node in assets.get_children():
		assets.remove_child(child)
		child.queue_free()
	for folder: String in catalog:
		var base: String = "res://generated/ali_assets/" + folder
		var manifest: String = base.path_join("asset.json")
		if not FileAccess.file_exists(manifest):
			continue
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest))
		if not parsed is Dictionary or str(parsed.get("scene", "")) != base.path_join("asset.tscn"):
			continue
		var button: Button = DragAsset.new()
		button.set("resource_path", str(parsed["scene"]))
		button.text = str(parsed.get("name", folder)) + " · 拖入场景"
		button.tooltip_text = str(parsed["scene"])
		button.pressed.connect(func() -> void: EditorInterface.get_file_system_dock().navigate_to_path(base.path_join("asset.tscn")))
		assets.add_child(button)


func _exit_tree() -> void:
	scene_changed.disconnect(sync_scene)
	if is_instance_valid(framework_wizard): framework_wizard.queue_free()
	if is_instance_valid(game_window):
		game_window.queue_free()
	if is_instance_valid(blueprint):
		blueprint.queue_free()
	refresh_timer.stop()
	remove_control_from_docks(dock)
	dock.queue_free()


func open_blueprint() -> void:
	if not is_instance_valid(blueprint):
		blueprint = BlueprintWindow.new()
		dock.add_child(blueprint)
		blueprint.connect("graph_applied", apply_blueprint)
	var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
	if selected.size() == 1:
		blueprint.call("bind_character", selected[0])
	blueprint.popup_centered(Vector2i(1280, 820))


func apply_blueprint(data: Dictionary) -> void:
	var character: Node = blueprint.get("target") as Node
	if not is_instance_valid(character):
		return
	var undo: EditorUndoRedoManager = get_undo_redo()
	undo.create_action("AlI应用角色蓝图", UndoRedo.MERGE_DISABLE, character)
	var values: Dictionary = {"blueprint": data, "use_project_actions": false,
		"four_way": data["settings"]["mode"] == "four_way", "platformer": data["settings"]["mode"] == "platformer"}
	for property: String in ["speed", "run_multiplier", "gravity", "jump_velocity"]:
		values[property] = data["settings"][property]
	for property: String in values:
		undo.add_do_property(character, property, values[property])
		undo.add_undo_property(character, property, character.get(property))
	var sprite: AnimatedSprite2D = character.get_node_or_null("AnimatedSprite2D") as AnimatedSprite2D
	var frames: SpriteFrames = blueprint.get("frames") as SpriteFrames
	if sprite != null and frames != null and sprite.sprite_frames != frames:
		undo.add_do_property(sprite, "sprite_frames", frames)
		undo.add_undo_property(sprite, "sprite_frames", sprite.sprite_frames)
	undo.commit_action()


func open_game_window() -> void:
	if not is_instance_valid(game_window):
		game_window = GameWindow.new()
		dock.add_child(game_window)
		game_window.connect("game_applied", apply_game)
	game_window.call("bind_selection")
	game_window.popup_centered(Vector2i(1500, 900))


func sync_scene(root: Node) -> void:
	if is_instance_valid(game_window): game_window.call("bind_scene",root)


func apply_game(target: Node, data: Dictionary) -> void:
	if not is_instance_valid(target):
		return
	var prepared: Dictionary = preload("game_library.gd").compile(data)
	if prepared.has("error"):
		push_warning(str(prepared["error"]))
		return
	var runtime: Node = Builder.scene_runtime(target)
	var undo: EditorUndoRedoManager = get_undo_redo()
	undo.create_action("AlI 应用场景蓝图", UndoRedo.MERGE_DISABLE, target)
	if runtime == null:
		runtime = Builder.new_runtime()
		add_scene_child(undo,target,runtime,target)
	var values: Dictionary = {"game_blueprint":data.duplicate(true),"compiled_blueprint":prepared["data"],"compiled_signature":prepared["signature"]}
	if "blueprint_resources" in runtime:
		var dependencies: Dictionary = {}
		collect_resources(prepared["data"]["nodes"],dependencies)
		var resources: Array[Resource] = []
		resources.assign(dependencies.values())
		values["blueprint_resources"] = resources
	for property: String in values:
		undo.add_do_property(runtime,property,values[property])
		undo.add_undo_property(runtime,property,runtime.get(property))
	if data.get("template") == "canvas":
		apply_visuals(undo,target,data)
	undo.commit_action()


func collect_resources(nodes: Array, found: Dictionary) -> void:
	for node: Dictionary in nodes:
		for field: Array in Model.fields(str(node["kind"])):
			if field[2] != "asset": continue
			var path: String = str(node["params"].get(field[0],""))
			if not path.is_empty() and not found.has(path) and ResourceLoader.exists(path):
				found[path] = load(path)
		if node.get("_subgraph") is Dictionary:
			collect_resources(node["_subgraph"]["nodes"],found)


func add_scene_child(undo: EditorUndoRedoManager, parent: Node, child: Node, scene: Node) -> void:
	undo.add_do_method(parent, "add_child", child, true)
	undo.add_do_method(child, "set_owner", scene)
	undo.add_undo_method(parent, "remove_child", child)
	undo.add_do_reference(child)


func apply_visuals(undo: EditorUndoRedoManager, root: Node, data: Dictionary) -> void:
	var touched: Dictionary = {}
	for node: Dictionary in data["nodes"]:
		var p: Dictionary = node["params"]
		if node["kind"] != "animation" or p.get("mode") != "frames" or str(p.get("frames","")).is_empty(): continue
		var path: String = str(p["target"])
		if touched.has(path): continue
		var source: SpriteFrames = Model.frames_at(str(p["frames"]))
		if source == null or not source.has_animation(str(p["clip"])): continue
		var sprite: AnimatedSprite2D = Access.node(root,path) as AnimatedSprite2D
		var created: bool = false
		if sprite == null and path.get_file() == "AlIVisual":
			var parent: Node = root if path.get_base_dir().is_empty() else Access.node(root,path.get_base_dir())
			if parent is CanvasItem and parent.get_node_or_null("AlIVisual") == null and (parent == root or parent.owner == root):
				sprite = AnimatedSprite2D.new()
				sprite.name = "AlIVisual"
				add_scene_child(undo,parent,sprite,root)
				created = true
		if sprite == null: continue
		touched[path] = true
		var frames: SpriteFrames = source
		if sprite.sprite_frames != null and sprite.sprite_frames != source:
			frames = sprite.sprite_frames.duplicate() as SpriteFrames
			preload("asset_drop.gd").copy_clip(frames,str(p["clip"]),source,str(p["clip"]))
		undo.add_do_property(sprite,"sprite_frames",frames)
		undo.add_do_property(sprite,"animation",p["clip"])
		if not created:
			undo.add_undo_property(sprite,"sprite_frames",sprite.sprite_frames)
			if sprite.sprite_frames != null and sprite.sprite_frames.has_animation(sprite.animation):
				undo.add_undo_property(sprite,"animation",sprite.animation)
