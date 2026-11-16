@tool
extends EditorPlugin

const DragAsset: GDScript = preload("asset_drag.gd")
var dock: VBoxContainer
var application: LineEdit
var kind: OptionButton
var assets: VBoxContainer
var status: Label
var refresh_timer: Timer
var chooser: FileDialog
var known_catalog: PackedStringArray = []
var catalog_initialized: bool = false
var blueprint: AcceptDialog
var binding_node: Node
var binding_property: String = ""
var binding_button: Button


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
	chooser = FileDialog.new()
	chooser.access = FileDialog.ACCESS_FILESYSTEM
	chooser.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	dock.add_child(chooser)
	browse.pressed.connect(func() -> void: chooser.popup_centered_ratio(0.65))
	chooser.dir_selected.connect(func(path: String) -> void: application.text = path)
	kind = OptionButton.new()
	for title: String in ["图片", "精灵动画", "游戏音效", "背景配乐"]:
		kind.add_item(title)
	dock.add_child(kind)
	var open_button: Button = Button.new()
	open_button.text = "打开生成窗口"
	open_button.pressed.connect(open_generator)
	dock.add_child(open_button)
	var edit_character: Button = Button.new()
	edit_character.text = "选中角色：动作／键位蓝图…"
	edit_character.pressed.connect(open_blueprint)
	dock.add_child(edit_character)
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
	if is_instance_valid(blueprint):
		blueprint.queue_free()
	refresh_timer.stop()
	remove_control_from_docks(dock)
	dock.queue_free()


func open_blueprint() -> void:
	var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
	if selected.size() != 1 or not "key_left" in selected[0]:
		status.text = "请选中导出的角色根节点，再打开蓝图。"
		return
	binding_node = selected[0]
	binding_property = ""
	if is_instance_valid(blueprint):
		blueprint.queue_free()
	blueprint = AcceptDialog.new()
	blueprint.title = "角色动作与键位蓝图"
	var content: VBoxContainer = VBoxContainer.new()
	blueprint.add_child(content)
	var hint: Label = Label.new()
	hint.text = "点击键位按钮后按新键。保存场景即可保留。\n动作动画在AnimatedSprite2D中编辑；攻击／跳跃／受击／死亡可连接角色信号。"
	content.add_child(hint)
	for entry: Array in [["左移", "key_left"], ["右移", "key_right"], ["上移", "key_up"], ["下移", "key_down"], ["奔跑", "key_run"], ["跳跃", "key_jump"], ["攻击", "key_attack"]]:
		var button: Button = Button.new()
		var property: String = str(entry[1])
		button.text = str(entry[0]) + "：" + OS.get_keycode_string(int(binding_node.get(property)))
		button.pressed.connect(func() -> void:
			binding_property = property
			binding_button = button
			button.text = "请按新键…")
		content.add_child(button)
	var speed_row: HBoxContainer = HBoxContainer.new()
	var speed_label: Label = Label.new()
	speed_label.text = "移动速度"
	speed_row.add_child(speed_label)
	var speed_input: SpinBox = SpinBox.new()
	speed_input.min_value = 1.0
	speed_input.max_value = 2000.0
	speed_input.value = float(binding_node.get("speed"))
	speed_input.value_changed.connect(func(value: float) -> void: set_blueprint_property("speed", value))
	speed_row.add_child(speed_input)
	content.add_child(speed_row)
	dock.add_child(blueprint)
	blueprint.confirmed.connect(func() -> void: binding_property = "")
	blueprint.canceled.connect(func() -> void: binding_property = "")
	blueprint.popup_centered(Vector2i(520, 460))


func set_blueprint_property(property: String, value: Variant) -> void:
	if not is_instance_valid(binding_node):
		return
	var undo: EditorUndoRedoManager = get_undo_redo()
	undo.create_action("AlI角色蓝图：" + property)
	undo.add_do_property(binding_node, property, value)
	undo.add_undo_property(binding_node, property, binding_node.get(property))
	undo.commit_action()


func _input(event: InputEvent) -> void:
	if binding_property.is_empty() or not is_instance_valid(blueprint) or not blueprint.visible:
		return
	if event is InputEventKey and event.pressed and not event.echo:
		set_blueprint_property(binding_property, event.physical_keycode)
		set_blueprint_property("use_project_actions", false)
		binding_button.text = binding_property.trim_prefix("key_") + "：" + OS.get_keycode_string(event.physical_keycode)
		binding_property = ""
		get_viewport().set_input_as_handled()
