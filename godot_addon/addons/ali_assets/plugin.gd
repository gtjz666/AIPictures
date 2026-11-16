@tool
extends EditorPlugin

const DragAsset: GDScript = preload("asset_drag.gd")
const BlueprintWindow: GDScript = preload("blueprint_window.gd")
const GameWindow: GDScript = preload("game_window.gd")
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



func _enter_tree() -> void:
	add_to_group("ali_assets_editor")
	dock = VBoxContainer.new()
	dock.name = "AlI 素材"
	dock.custom_minimum_size.x = 240
	var label: Label = Label.new()
	label.text = "本地游戏素材生成"
	dock.add_child(label)
	application = LineEdit.new()
	application.placeholder_text = "AlI 软件文件夹"
	dock.add_child(application)
	var config: Variant = JSON.parse_string(FileAccess.get_file_as_string(get_script().resource_path.get_base_dir().path_join("application.json"))) if FileAccess.file_exists(get_script().resource_path.get_base_dir().path_join("application.json")) else null
	if config is Dictionary:
		application.text = str(config.get("root", ""))
	var remembered: String = str(EditorInterface.get_editor_settings().get_project_metadata("ali_assets", "application_root", ""))
	if not remembered.is_empty():
		application.text = remembered
	var browse: Button = Button.new()
	browse.text = "选择软件目录…"
	dock.add_child(browse)
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
	var edit_character: Button = Button.new()
	edit_character.text = "角色蓝图工作台…"
	edit_character.pressed.connect(open_blueprint)
	dock.add_child(edit_character)
	var edit_game: Button = Button.new()
	edit_game.text = "游戏蓝图／创建小游戏…"
	edit_game.pressed.connect(open_game_window)
	dock.add_child(edit_game)
	set_process_input(true)
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.text = "单一提示词输入；在外置窗口生成、预览并导出组件。"
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
	refresh_assets.call_deferred()


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
	var directory: DirAccess = DirAccess.open("res://generated/ali_assets")
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
	undo.commit_action()


func open_game_window() -> void:
	if not is_instance_valid(game_window):
		game_window = GameWindow.new()
		dock.add_child(game_window)
		game_window.connect("game_applied", apply_game)
	game_window.popup_centered(Vector2i(1500, 900))


func apply_game(target: Node, data: Dictionary) -> void:
	if not is_instance_valid(target):
		return
	var undo: EditorUndoRedoManager = get_undo_redo()
	undo.create_action("AlI应用游戏蓝图", UndoRedo.MERGE_DISABLE, target)
	undo.add_do_property(target, "game_blueprint", data.duplicate(true))
	undo.add_undo_property(target, "game_blueprint", target.get("game_blueprint"))
	undo.commit_action()
