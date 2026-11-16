@tool
extends Window
signal game_applied(target: Node, data: Dictionary)
const Model: GDScript = preload("game_model.gd")
const Library: GDScript = preload("game_library.gd")
const Registry: GDScript = preload("game_registry.gd")
const Builder: GDScript = preload("game_builder.gd")
var data: Dictionary = Model.preset()
var graph: GraphEdit
var inspector: VBoxContainer
var message: Label
var target_label: Label
var target: Node
var selected_id: String = "session"
var history: UndoRedo = UndoRedo.new()
var chooser: FileDialog
var operation: String = ""
var pending_field: String = ""
var capture_field: String = ""
var dirty: bool = false
var startup: CheckBox
var palette: Window
var search: LineEdit
var results: ItemList
var palette_source: String = ""
var palette_port: int = 0
var palette_position: Vector2 = Vector2.ZERO
var module_draft: Dictionary = {}
var navigator: OptionButton


func _init() -> void:
	visible = false
	force_native = true


func _exit_tree() -> void:
	history.clear_history()
	history.free()


func _ready() -> void:
	title = "AlI · 游戏蓝图工作台"
	min_size = Vector2i(1100, 700)
	size = Vector2i(1500, 900)
	close_requested.connect(hide)
	window_input.connect(on_input)
	var root: VBoxContainer = VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(root)
	var toolbar: HBoxContainer = HBoxContainer.new()
	root.add_child(toolbar)
	button(toolbar, "新建横版跳跃模板", func() -> void: change("新建模板", Model.preset()))
	button(toolbar, "新建通用2D模板", func() -> void: change("新建通用模板", Model.scene_preset()))
	button(toolbar, "+ 搜索模块…", func() -> void: open_palette())
	var combos: MenuButton = MenuButton.new()
	combos.text = "+ 常用组合 ▾"
	combos.get_popup().add_item("生命值／受伤／恢复／死亡（J／K）", 0)
	combos.get_popup().add_item("状态机／攻击冷却示例（F）", 1)
	combos.get_popup().id_pressed.connect(func(index: int) -> void: change("添加常用组合", Model.add_combo(data, "health" if index == 0 else "fsm")))
	toolbar.add_child(combos)
	button(toolbar, "撤销", func() -> void: history.undo())
	button(toolbar, "重做", func() -> void: history.redo())
	button(toolbar, "打开蓝图…", func() -> void: choose("load"))
	button(toolbar, "保存蓝图…", func() -> void: choose("save"))
	var tools: HBoxContainer = HBoxContainer.new()
	root.add_child(tools)
	toolbar = tools
	button(toolbar, "编译检查", check_graph)
	button(toolbar, "保存所选为子图…", save_module)
	button(toolbar, "执行记录", show_debug)
	button(toolbar, "创建游戏场景…", func() -> void: choose("scene"))
	button(toolbar, "绑定当前游戏", bind_selection)
	button(toolbar, "应用到游戏", apply_game)
	var options: HBoxContainer = HBoxContainer.new()
	root.add_child(options)
	startup = CheckBox.new()
	startup.text = "创建后设为项目启动场景"
	options.add_child(startup)
	target_label = Label.new()
	target_label.text = "未绑定 · 模板已连好，先创建场景，再按F6运行。"
	options.add_child(target_label)
	navigator = OptionButton.new()
	navigator.custom_minimum_size.x = 210
	navigator.tooltip_text = "快速选择并定位模块"
	navigator.item_selected.connect(func(index: int) -> void:
		selected_id = str(navigator.get_item_metadata(index))
		show_inspector()
		var node: Dictionary = Model.find(data, selected_id)
		graph.scroll_offset = Vector2(float(node["position"][0]), float(node["position"][1])) * graph.zoom - graph.size / 2 + Vector2(140, 80)
		for child: Node in graph.get_children():
			if child is GraphNode:
				(child as GraphNode).selected = str(child.name) == selected_id)
	options.add_child(navigator)
	var hint: Label = Label.new()
	hint.text = "点击模块，在右侧改参数／选素材。白色执行／绿色布尔／蓝色数字／粉色文字。拖线到空白处可搜索兼容模块。默认素材与声音为原创演示占位，可逐项替换。"
	root.add_child(hint)
	var split: HSplitContainer = HSplitContainer.new()
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(split)
	graph = GraphEdit.new()
	graph.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	graph.right_disconnects = true
	graph.zoom = 0.75
	graph.connection_request.connect(connect_modules)
	graph.disconnection_request.connect(disconnect_modules)
	graph.delete_nodes_request.connect(delete_modules)
	graph.popup_request.connect(func(at: Vector2) -> void: open_palette("", 0, at))
	graph.connection_to_empty.connect(func(source: StringName, port: int, at: Vector2) -> void: open_palette(str(source), port, at))
	split.add_child(graph)
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.custom_minimum_size.x = 320
	inspector = VBoxContainer.new()
	inspector.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(inspector)
	split.add_child(scroll)
	message = Label.new()
	message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	root.add_child(message)
	chooser = FileDialog.new()
	chooser.access = FileDialog.ACCESS_RESOURCES
	chooser.force_native = true
	chooser.file_selected.connect(file_selected)
	add_child(chooser)
	setup_palette()
	render()


func button(parent: Node, text: String, callback: Callable) -> Button:
	var result: Button = Button.new()
	result.text = text
	result.pressed.connect(callback)
	parent.add_child(result)
	return result


func change(label: String, next: Dictionary, refresh: bool = true) -> bool:
	var problem: String = Model.validate(next)
	if not problem.is_empty():
		message.text = problem
		return false
	history.create_action(label)
	history.add_do_method(assign.bind(next.duplicate(true)))
	history.add_undo_method(assign.bind(data.duplicate(true)))
	history.commit_action(false)
	assign(next, refresh)
	return true


func assign(next: Dictionary, refresh: bool = true) -> void:
	data = next.duplicate(true)
	dirty = true
	capture_field = ""
	render(refresh)
	message.text = "修改已记录；请应用到现有游戏并保存场景，或创建新场景。"


func render(refresh: bool = true) -> void:
	if graph == null:
		return
	graph.clear_connections()
	navigator.clear()
	for node: Dictionary in data["nodes"]:
		var index: int = navigator.item_count
		navigator.add_item(str(Model.TITLES[node["kind"]]) + (" · " + Model.summary(node) if not Model.summary(node).is_empty() else ""))
		navigator.set_item_metadata(index, str(node["id"]))
		if str(node["id"]) == selected_id:
			navigator.select(index)
	for child: Node in graph.get_children():
		if child is GraphNode:
			graph.remove_child(child)
			child.queue_free()
	for node: Dictionary in data["nodes"]:
		var widget: GraphNode = GraphNode.new()
		var id: String = str(node["id"])
		var kind: String = str(node["kind"])
		widget.name = id
		widget.title = str(Model.TITLES[kind]) + (" · " + Model.summary(node) if not Model.summary(node).is_empty() else "")
		widget.tooltip_text = "模块编号：" + id
		widget.custom_minimum_size.x = 260
		widget.position_offset = Vector2(float(node["position"][0]), float(node["position"][1]))
		var style: StyleBoxFlat = StyleBoxFlat.new()
		style.bg_color = Color("3b647a") if kind in Model.SINGLETONS else Color("725587") if kind == "custom" else Color("7a5741") if kind == "audio" else Color("4b7963") if kind == "boolean" else Color("655c64")
		style.set_content_margin_all(8)
		widget.add_theme_stylebox_override("titlebar", style)
		graph.add_child(widget)
		widget.node_selected.connect(func() -> void:
			selected_id = id
			navigator.select(data["nodes"].find(node))
			show_inspector())
		widget.dragged.connect(func(_from: Vector2, to: Vector2) -> void:
			var next: Dictionary = data.duplicate(true)
			Model.find(next, id)["position"] = [to.x, to.y]
			change("移动模块", next))
		var ins: Array = Model.INPUTS[kind]
		var outs: Array = Model.OUTPUTS[kind]
		for index: int in range(maxi(1, maxi(ins.size(), outs.size()))):
			var row: HBoxContainer = HBoxContainer.new()
			var left: Label = Label.new()
			left.text = str(ins[index]) if index < ins.size() else ""
			left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_child(left)
			var right: Label = Label.new()
			right.text = str(outs[index]) if index < outs.size() else ""
			row.add_child(right)
			widget.add_child(row)
			var left_type: int = Registry.port_type(kind, node["params"], index, false)
			var right_type: int = Registry.port_type(kind, node["params"], index, true)
			widget.set_slot(index, index < ins.size(), left_type, Model.color_for(left_type), index < outs.size(), right_type, Model.color_for(right_type))
		if ins.is_empty() and outs.is_empty():
			(widget.get_child(0).get_child(0) as Label).text = "选择此模块配置参数"
	for edge: Dictionary in data["edges"]:
		graph.connect_node(str(edge["from"]), int(edge.get("from_port", 0)), str(edge["to"]), int(edge.get("to_port", 0)))
	if refresh:
		show_inspector()


func show_inspector() -> void:
	for child: Node in inspector.get_children():
		inspector.remove_child(child)
		child.queue_free()
	var node: Dictionary = Model.find(data, selected_id)
	if node.is_empty():
		return
	var kind: String = str(node["kind"])
	var title: Label = Label.new()
	title.text = str(Model.TITLES[kind])
	title.add_theme_font_size_override("font_size", 20)
	inspector.add_child(title)
	for field: Array in Model.fields(kind):
		if kind in ["blackboard", "set_variable"] and field[0] in ["bool", "number", "text"] and field[0] != node["params"]["value_type"]:
			continue
		var name: String = str(field[0])
		var type: String = str(field[2])
		var value: Variant = node["params"][name]
		var caption: Label = Label.new()
		caption.text = str(field[1])
		inspector.add_child(caption)
		match type:
			"number", "integer":
				var spin: SpinBox = SpinBox.new()
				spin.min_value = float(field[4])
				spin.max_value = float(field[5])
				spin.step = 1 if type == "integer" or float(field[5]) > 100 else 0.01
				spin.value = float(value)
				spin.value_changed.connect(func(next: float) -> void: parameter(name, next))
				inspector.add_child(spin)
			"bool":
				var check: CheckBox = CheckBox.new()
				check.text = "启用"
				check.button_pressed = bool(value)
				check.toggled.connect(func(next: bool) -> void: parameter(name, next))
				inspector.add_child(check)
			"choice":
				var choice: OptionButton = OptionButton.new()
				var keys: Array = field[4].keys()
				for key: String in keys:
					choice.add_item(str(field[4][key]))
				choice.selected = keys.find(value)
				choice.item_selected.connect(func(index: int) -> void: parameter(name, keys[index]))
				inspector.add_child(choice)
			"asset":
				var row: HBoxContainer = HBoxContainer.new()
				var pick: Button = button(row, "选择…" if str(value).is_empty() else str(value).get_file(), func() -> void:
					pending_field = name
					choose("scene_asset" if field[4] == "scene" else str(field[4])))
				pick.tooltip_text = str(value)
				button(row, "清空", func() -> void: parameter(name, ""))
				inspector.add_child(row)
				if field[4] == "script":
					button(inspector, "新建可编写模块…", func() -> void:
						pending_field = name
						choose("new_script"))
					if not str(value).is_empty():
						button(inspector, "在Godot中编辑脚本", func() -> void: EditorInterface.edit_script(load(str(value)) as Script))
			"key":
				var common: OptionButton = OptionButton.new()
				var keys: Array[int] = [KEY_SPACE, KEY_ESCAPE, KEY_ENTER, KEY_UP, KEY_W, KEY_A, KEY_S, KEY_D, KEY_J, KEY_K, KEY_R, KEY_P]
				if not int(value) in keys:
					keys.append(int(value))
				for key: int in keys:
					common.add_item(OS.get_keycode_string(key))
				common.selected = keys.find(int(value))
				common.item_selected.connect(func(index: int) -> void: parameter(name, keys[index]))
				inspector.add_child(common)
				button(inspector, OS.get_keycode_string(int(value)) + " · 点击改键", func() -> void:
					capture_field = name
					message.text = "请按新键，Esc取消。")
			"color":
				var color: ColorPickerButton = ColorPickerButton.new()
				color.color = Color(str(value))
				color.color_changed.connect(func(next: Color) -> void: parameter(name, next.to_html()))
				inspector.add_child(color)
			_:
				var edit: LineEdit = LineEdit.new()
				edit.text = str(value)
				edit.text_submitted.connect(func(next: String) -> void: parameter(name, next.strip_edges()))
				inspector.add_child(edit)


func parameter(field: String, value: Variant) -> void:
	if Model.find(data, selected_id)["params"].get(field) == value:
		return
	var next: Dictionary = data.duplicate(true)
	Model.find(next, selected_id)["params"][field] = value
	if not change("修改参数", next, field == "value_type"):
		show_inspector()


func on_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if not capture_field.is_empty():
			if event.keycode != KEY_ESCAPE:
				parameter(capture_field, event.physical_keycode if event.physical_keycode != 0 else event.keycode)
			capture_field = ""
			get_viewport().set_input_as_handled()
		elif event.ctrl_pressed and event.keycode == KEY_Z:
			history.redo() if event.shift_pressed else history.undo()
			get_viewport().set_input_as_handled()


func add_module(kind: String) -> void:
	var next: Dictionary = data.duplicate(true)
	var id: String = "module_" + str(Time.get_ticks_usec())
	var node: Dictionary = Model.module(id, kind, graph.scroll_offset.x + 100, graph.scroll_offset.y + 100)
	if kind in ["boolean", "blackboard", "fsm"]:
		node["params"]["name"] = id
	next["nodes"].append(node)
	if change("添加模块", next):
		selected_id = id
		show_inspector()


func connect_modules(source: StringName, from_port: int, dest: StringName, to_port: int) -> void:
	var next: Dictionary = data.duplicate(true)
	next["edges"].append({"from": str(source), "from_port": from_port, "to": str(dest), "to_port": to_port})
	change("连接模块", next)


func disconnect_modules(source: StringName, from_port: int, dest: StringName, to_port: int) -> void:
	var next: Dictionary = data.duplicate(true)
	next["edges"] = next["edges"].filter(func(edge: Dictionary) -> bool: return edge["from"] != str(source) or edge["to"] != str(dest) or int(edge.get("from_port", 0)) != from_port or int(edge.get("to_port", 0)) != to_port)
	change("断开模块", next)


func delete_modules(ids: Array[StringName]) -> void:
	var next: Dictionary = data.duplicate(true)
	next["nodes"] = next["nodes"].filter(func(node: Dictionary) -> bool: return not StringName(node["id"]) in ids)
	next["edges"] = next["edges"].filter(func(edge: Dictionary) -> bool: return not StringName(edge["from"]) in ids and not StringName(edge["to"]) in ids)
	change("删除模块", next)


func bind_selection() -> void:
	var nodes: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
	if nodes.size() != 1 or not "game_blueprint" in nodes[0]:
		message.text = "请选中创建的RunnerGame游戏根节点。"
		return
	if dirty:
		if is_instance_valid(target) and target != nodes[0]:
			message.text = "请先保存或应用当前修改，再更换绑定游戏。"
			return
		target = nodes[0]
		target_label.text = "已绑定：" + str(target.name)
		message.text = "当前草稿已保留；点击应用到游戏，再保存场景。"
		return
	target = nodes[0]
	var stored: Dictionary = target.get("game_blueprint")
	var problem: String = Model.validate(stored)
	if not problem.is_empty():
		message.text = problem
		return
	data = stored.duplicate(true)
	history.clear_history()
	target_label.text = "已绑定：" + str(target.name)
	render()


func apply_game() -> void:
	if not is_instance_valid(target):
		message.text = "请先绑定游戏根节点，或创建新场景。"
		return
	if not "compiled_blueprint" in target:
		message.text = "此场景使用旧运行模块。草稿已保留，请创建新名称的游戏场景升级；旧场景不会覆盖。"
		return
	var prepared: Dictionary = Library.compile(data)
	var problem: String = str(prepared.get("error", ""))
	if not problem.is_empty():
		message.text = problem
		return
	game_applied.emit(target, data.duplicate(true))
	dirty = false
	message.text = "已应用；请保存Godot场景，再运行。"


func choose(kind: String) -> void:
	operation = kind
	chooser.file_mode = FileDialog.FILE_MODE_SAVE_FILE if kind in ["save", "scene", "new_script", "save_module"] else FileDialog.FILE_MODE_OPEN_FILE
	chooser.filters = PackedStringArray(["*.tscn ; 游戏场景"]) if kind in ["scene", "scene_asset"] else PackedStringArray(["*.json ; 蓝图／子图"]) if kind in ["save", "load", "module", "save_module"] else PackedStringArray(["*.gd ; 自定义模块"]) if kind in ["script", "new_script"] else PackedStringArray(["*.tscn,*.tres ; 角色动画资源"]) if kind == "frames" else PackedStringArray(["*.wav,*.ogg,*.mp3 ; 音频"]) if kind == "audio" else PackedStringArray(["*.png,*.jpg,*.webp ; 图片"])
	if kind in ["scene", "save", "new_script", "save_module"]:
		chooser.current_file = "runner_game.tscn" if kind == "scene" else "runner_blueprint.json" if kind == "save" else "flow_module.json" if kind == "save_module" else "game_module.gd"
	chooser.popup_centered(Vector2i(850, 560))


func file_selected(path: String) -> void:
	if not path.begins_with("res://") or ".." in path:
		message.text = "请选择当前项目内位置。"
		return
	if operation == "scene":
		var problem: String = Builder.create_scene(data, path)
		if not problem.is_empty():
			message.text = problem
			return
		dirty = false
		target = null
		target_label.text = "新场景已创建；请选择RunnerGame并绑定以继续编辑。"
		if startup.button_pressed:
			ProjectSettings.set_setting("application/run/main_scene", path)
			ProjectSettings.save()
		EditorInterface.get_resource_filesystem().scan()
		EditorInterface.open_scene_from_path(path)
		message.text = "已创建完整游戏；选中游戏根节点绑定后继续修改，按F6运行。"
	elif operation == "save_module":
		if FileAccess.file_exists(path):
			message.text = "子图已存在，请使用新名称。"
			return
		var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(module_draft, "\t"))
			file.close()
			message.text = "子图已保存；搜索“可复用子图”并选择此文件即可调用。"
	elif operation == "save":
		var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(data, "\t"))
			file.close()
			dirty = false
			message.text = "蓝图已保存；应用到游戏后仍需保存场景。"
	elif operation == "load":
		if FileAccess.get_file_as_bytes(path).size() > 1024 * 1024:
			message.text = "文件超过1MB。"
			return
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if parsed is Dictionary:
			change("打开蓝图", parsed)
		else:
			message.text = "不是有效的游戏蓝图。"
	else:
		if operation == "new_script":
			if FileAccess.file_exists(path):
				message.text = "文件已存在，请使用新名称。"
				return
			var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
			if file == null:
				return
			file.store_string(FileAccess.get_file_as_string(get_script().resource_path.get_base_dir().path_join("custom_module_template.gd")))
			file.close()
		parameter(pending_field, path)


func setup_palette() -> void:
	palette = Window.new()
	palette.visible = false
	palette.force_native = true
	palette.title = "搜索模块 · 可输入名称或类别"
	palette.close_requested.connect(palette.hide)
	var box: VBoxContainer = VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	palette.add_child(box)
	search = LineEdit.new()
	search.placeholder_text = "例如：状态、生命、事件、场景、变量"
	search.text_changed.connect(func(_text: String) -> void: filter_palette())
	search.text_submitted.connect(func(_text: String) -> void:
		if results.item_count > 0:
			add_palette_item(0))
	box.add_child(search)
	results = ItemList.new()
	results.size_flags_vertical = Control.SIZE_EXPAND_FILL
	results.item_activated.connect(add_palette_item)
	box.add_child(results)
	button(box, "添加所选模块", func() -> void:
		var selected: PackedInt32Array = results.get_selected_items()
		if not selected.is_empty():
			add_palette_item(selected[0]))
	add_child(palette)


func open_palette(source: String = "", port: int = 0, at: Vector2 = Vector2.ZERO) -> void:
	palette_source = source
	palette_port = port
	palette_position = (graph.scroll_offset + (at if at != Vector2.ZERO else Vector2(120, 120))) / graph.zoom
	search.text = ""
	filter_palette()
	palette.popup_centered(Vector2i(540, 580))
	search.grab_focus()


func filter_palette() -> void:
	results.clear()
	var term: String = search.text.strip_edges().to_lower()
	for kind: String in Model.TITLES:
		var label: String = Registry.category(kind) + " · " + str(Model.TITLES[kind])
		if not term.is_empty() and not term in label.to_lower() and not term in kind:
			continue
		if kind in Model.SINGLETONS and not Model.by_kind(data, kind).is_empty():
			continue
		if not palette_source.is_empty():
			var compatible: bool = false
			for port: int in range(Model.INPUTS[kind].size()):
				if Registry.port_type(kind, Model.params(kind), port, false) == Model.port_type(data, palette_source, palette_port, true):
					compatible = true
			if not compatible:
				continue
		var index: int = results.add_item(label)
		results.set_item_metadata(index, kind)


func add_palette_item(index: int) -> void:
	var kind: String = str(results.get_item_metadata(index))
	var next: Dictionary = data.duplicate(true)
	var id: String = "module_" + str(Time.get_ticks_usec())
	var node: Dictionary = Model.module(id, kind, palette_position.x, palette_position.y)
	if kind in ["boolean", "blackboard", "fsm"]:
		node["params"]["name"] = id
	next["nodes"].append(node)
	if not palette_source.is_empty():
		for port: int in range(Model.INPUTS[kind].size()):
			if Registry.port_type(kind, node["params"], port, false) == Model.port_type(data, palette_source, palette_port, true):
				next["edges"].append({"from": palette_source, "from_port": palette_port, "to": id, "to_port": port})
				break
	if change("添加并连接模块", next):
		selected_id = id
		show_inspector()
		palette.hide()


func check_graph() -> void:
	var prepared: Dictionary = Library.compile(data)
	if prepared.has("error"):
		message.text = "编译未通过：" + str(prepared["error"])
		var id: String = str(prepared["error"]).get_slice("：", 0)
		if not Model.find(data, id).is_empty():
			selected_id = id
			show_inspector()
	else:
		message.text = "编译通过 · 展开后%d个模块、%d条连线。应用到游戏后保存场景；修改子图文件后需重新应用。" % [prepared["data"]["nodes"].size(), prepared["data"]["edges"].size()]


func save_module() -> void:
	var selected: Array[String] = []
	for child: Node in graph.get_children():
		if child is GraphNode and (child as GraphNode).selected:
			selected.append(str(child.name))
	var result: Dictionary = Library.extract(data, selected)
	if result.has("error"):
		message.text = str(result["error"])
		return
	module_draft = result["data"]
	choose("save_module")


func show_debug() -> void:
	var path: String = "user://ali_blueprint_" + str(Model.by_kind(data, "session")["params"]["save_key"]) + ".json"
	if not FileAccess.file_exists(path):
		message.text = "尚无执行记录。运行并退出此游戏场景后再打开；发行版不写调试记录。"
		return
	var dialog: AcceptDialog = AcceptDialog.new()
	dialog.title = "最近一次执行 · 变量／状态／生命值／最多256条事件"
	var text: TextEdit = TextEdit.new()
	text.editable = false
	text.custom_minimum_size = Vector2(850, 550)
	text.text = FileAccess.get_file_as_string(path)
	dialog.add_child(text)
	add_child(dialog)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered()
