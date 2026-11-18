@tool
extends Window
signal game_applied(target: Node, data: Dictionary)
const Model: GDScript = preload("game_model.gd")
const Library: GDScript = preload("game_library.gd")
const Registry: GDScript = preload("game_registry.gd")
const Link: GDScript = preload("resource_link.gd")
const Slot: GDScript = preload("resource_slot.gd")
const Drop: GDScript = preload("asset_drop.gd")
const Groups: GDScript = preload("inspector_groups.gd")
const ButtonPreview: GDScript = preload("button_preview.gd")
const Browser: GDScript = preload("resource_browser.gd")
const Builder: GDScript = preload("game_builder.gd")
const EditorTools: GDScript = preload("game_editor_tools.gd")
const InputDefinitions: GDScript = preload("framework_input.gd")
const NodeSlot: GDScript = preload("node_slot.gd")
const Access: GDScript = preload("blueprint_access.gd")
const ImportWizard: GDScript = preload("asset_import_wizard.gd")
const AnimationPreview: GDScript = preload("animation_preview.gd")
const ParameterLibrary: GDScript = preload("subgraph_library.gd")
const TilePicker: GDScript = preload("tile_picker.gd")
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
var favorites: Array = []
var favorites_only: bool = false
var moving_nodes: bool = false
var move_draft: Dictionary = {}
var debug_timer: Timer
var debug_list: ItemList
var debug_snapshot: Dictionary = {}


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
	files_dropped.connect(on_files_dropped)
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
	button(toolbar, "动画／图集导入…", func() -> void:
		var wizard: Window = ImportWizard.new()
		add_child(wizard)
		wizard.popup_centered())
	button(toolbar, "复制", copy_selected)
	button(toolbar, "粘贴", paste_nodes)
	button(toolbar, "资源预览…", func() -> void:
		var browser: Window = Browser.new()
		add_child(browser)
		browser.popup_centered())
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
	graph.copy_nodes_request.connect(copy_selected)
	graph.paste_nodes_request.connect(paste_nodes)
	graph.begin_node_move.connect(func() -> void: moving_nodes = true; move_draft = data.duplicate(true))
	graph.end_node_move.connect(func() -> void:
		moving_nodes = false
		for widget: Node in graph.get_children():
			if widget is GraphNode: Model.find(move_draft,str(widget.name))["position"] = [widget.position_offset.x,widget.position_offset.y]
		if move_draft != data: change("移动所选模块",move_draft)
		move_draft = {})
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
	if Engine.is_editor_hint(): favorites = EditorInterface.get_editor_settings().get_project_metadata("ali_assets","favorites",[])
	debug_timer = Timer.new()
	debug_timer.wait_time = 0.5
	debug_timer.timeout.connect(poll_debug)
	add_child(debug_timer)
	debug_timer.start()
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
	data = Link.normalize(Model.upgrade(next))
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
		widget.tooltip_text = EditorTools.description(kind)+"\n模块编号："+id
		widget.custom_minimum_size.x = 260
		widget.position_offset = Vector2(float(node["position"][0]), float(node["position"][1]))
		var style: StyleBoxFlat = StyleBoxFlat.new()
		style.bg_color = Color("3b647a") if kind in Model.SINGLETONS else Color("725587") if kind == "custom" else Color("7a5741") if kind == "audio" else Color("4b7963") if kind == "boolean" else Color("655c64")
		style.set_content_margin_all(8)
		widget.add_theme_stylebox_override("titlebar", style)
		graph.add_child(widget)
		widget.set_drag_forwarding(Callable(),
			func(_point: Vector2, payload: Variant) -> bool: return compatible_fields(id, Drop.from_drag(payload)).size() == 1,
			func(_point: Vector2, payload: Variant) -> void: bind_dropped_asset(id, Drop.from_drag(payload)))
		widget.node_selected.connect(func() -> void:
			selected_id = id
			navigator.select(data["nodes"].find(node))
			show_inspector())
		widget.dragged.connect(func(_from: Vector2, to: Vector2) -> void:
			if moving_nodes: return
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
			var left_type: int = Model.port_type(data, id, index, false)
			var right_type: int = Model.port_type(data, id, index, true)
			widget.set_slot(index, index < ins.size(), left_type, Model.color_for(left_type), index < outs.size(), right_type, Color.ORANGE if EditorTools.event_output(kind,index) else Model.color_for(right_type))
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
	var description: Label = Label.new()
	description.text = EditorTools.description(kind)
	description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	inspector.add_child(description)
	button(inspector,"★ 取消收藏" if kind in favorites else "☆ 收藏此类模块",func() -> void:
		if kind in favorites: favorites.erase(kind)
		else: favorites.append(kind)
		if Engine.is_editor_hint(): EditorInterface.get_editor_settings().set_project_metadata("ali_assets","favorites",favorites)
		show_inspector())
	var groups: Dictionary = {}
	for field: Array in Model.fields(kind):
		if not EditorTools.visible_field(node,str(field[0])): continue
		var name: String = str(field[0])
		var type: String = str(field[2])
		var value: Variant = node["params"][name]
		var group: String = field_group(kind, name, type, field)
		if not groups.has(group):
			groups[group] = Groups.add(inspector, "game:" + kind + ":" + group, group)
		var body: VBoxContainer = groups[group]
		var caption: Label = Label.new()
		caption.text = str(field[1])
		caption.tooltip_text = EditorTools.field_hint(kind,field)
		body.add_child(caption)
		match type:
			"node":
				var slot: HBoxContainer = NodeSlot.new()
				body.add_child(slot)
				slot.call("setup",target,str(value))
				slot.connect("value_changed",func(path: String) -> void: parameter(name,path))
				slot.connect("node_chosen",func(_path: String, chosen: Node) -> void:
					if kind == "animation" and name == "target":
						if chosen is AnimationPlayer: parameter("mode","animation")
						elif chosen is AnimatedSprite2D: parameter("mode","frames")
						show_inspector())
			"json":
				var edit: TextEdit = TextEdit.new()
				edit.text = str(value)
				edit.custom_minimum_size = Vector2(260,90)
				body.add_child(edit)
				button(body,"应用JSON",func() -> void: parameter(name,edit.text.strip_edges()))
			"property":
				var properties: OptionButton = OptionButton.new()
				var bound: Node = Access.node(target,str(node["params"].get("target",""))) if is_instance_valid(target) else null
				var names: Array[String] = []
				for property: String in Access.PROPERTIES:
					if bound == null or Access.has_property(bound,property): names.append(property)
				if not str(value) in names: names.append(str(value))
				for property: String in names: properties.add_item(property)
				properties.select(names.find(str(value)))
				properties.item_selected.connect(func(index: int) -> void: parameter(name,names[index]))
				body.add_child(properties)
			"input_action":
				var actions: OptionButton = OptionButton.new()
				var names: Array[String] = []
				for action: StringName in InputMap.get_actions():
					if not str(action).begins_with("ui_"): names.append(str(action))
				for action: String in InputDefinitions.DEFAULTS:
					if not action in names: names.append(action)
				if not str(value) in names: names.append(str(value))
				for action: String in names: actions.add_item(action)
				actions.select(names.find(str(value)))
				actions.item_selected.connect(func(index: int) -> void: parameter(name,names[index]))
				body.add_child(actions)
				var custom: LineEdit = LineEdit.new()
				custom.text = str(value)
				custom.placeholder_text = "自定义InputMap动作名称"
				custom.text_submitted.connect(func(next: String) -> void: parameter(name,next.strip_edges()))
				body.add_child(custom)
			"number", "integer":
				var spin: SpinBox = SpinBox.new()
				spin.min_value = float(field[4])
				spin.max_value = float(field[5])
				spin.step = 1 if type == "integer" else 0.01
				spin.value = float(value)
				spin.value_changed.connect(func(next: float) -> void: parameter(name, next))
				body.add_child(spin)
			"bool":
				var check: CheckBox = CheckBox.new()
				check.text = "启用"
				check.button_pressed = bool(value)
				check.toggled.connect(func(next: bool) -> void: parameter(name, next))
				body.add_child(check)
			"choice":
				var choice: OptionButton = OptionButton.new()
				var keys: Array = field[4].keys()
				for key: String in keys:
					choice.add_item(str(field[4][key]))
				choice.selected = keys.find(value)
				choice.item_selected.connect(func(index: int) -> void: parameter(name, keys[index]))
				body.add_child(choice)
			"asset":
				var slot: VBoxContainer = Slot.new()
				body.add_child(slot)
				slot.call("setup", str(field[4]), str(value))
				slot.connect("value_changed", func(path: String) -> void: parameter(name, path))
				if field[4] == "script":
					button(body, "新建可编写模块…", func() -> void:
						pending_field = name
						choose("new_script"))
					if not str(value).is_empty():
						button(body, "在Godot中编辑脚本", func() -> void: EditorInterface.edit_script(load(str(value)) as Script))
			"key":
				var common: OptionButton = OptionButton.new()
				var keys: Array[int] = [KEY_SPACE, KEY_ESCAPE, KEY_ENTER, KEY_UP, KEY_W, KEY_A, KEY_S, KEY_D, KEY_J, KEY_K, KEY_R, KEY_P]
				if not int(value) in keys:
					keys.append(int(value))
				for key: int in keys:
					common.add_item(OS.get_keycode_string(key))
				common.selected = keys.find(int(value))
				common.item_selected.connect(func(index: int) -> void: parameter(name, keys[index]))
				body.add_child(common)
				button(body, OS.get_keycode_string(int(value)) + " · 点击改键", func() -> void:
					capture_field = name
					message.text = "请按新键，Esc取消。")
			"color":
				var color: ColorPickerButton = ColorPickerButton.new()
				color.color = Color(str(value))
				color.color_changed.connect(func(next: Color) -> void: parameter(name, next.to_html()))
				body.add_child(color)
			_:
				if kind == "animation" and name == "clip":
					var clips: Array[String] = animation_clips(node["params"])
					if not clips.is_empty():
						if not str(value) in clips: clips.push_front(str(value))
						var choice: OptionButton = OptionButton.new()
						for clip: String in clips: choice.add_item(clip)
						choice.select(clips.find(str(value)))
						choice.item_selected.connect(func(index: int) -> void: parameter(name,clips[index]))
						body.add_child(choice)
						continue
				var edit: LineEdit = LineEdit.new()
				edit.text = str(value)
				edit.text_submitted.connect(func(next: String) -> void: parameter(name, next.strip_edges()))
				body.add_child(edit)

	if kind == "button":
		var events: VBoxContainer = Groups.add(inspector, "game:button:events", "事件与预览")
		var hint: Label = Label.new()
		hint.text = "从节点右侧连接：点击、按下、释放、鼠标进入／离开。\n悬停／按下／点击动效复用通用动画服务，可配置或关闭。"
		hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		events.add_child(hint)
		button(events, "预览四状态按钮…", func() -> void:
			var prepared: Dictionary = Library.compile(data)
			if prepared.has("error"):
				message.text = prepared["error"]
				return
			var preview: Window = ButtonPreview.new()
			add_child(preview)
			preview.call("present", node["params"].duplicate(true)))
	if kind in ["animation","camera2d"]:
		button(inspector,"▶ 独立预览／复位…",func() -> void:
			var preview: Window = AnimationPreview.new()
			add_child(preview)
			preview.call("present",target,node))
	if kind == "camera2d":
		for row: Array in [["平台跟随",5.0],["俯视跟随",8.0],["即时跟随",0.0]]:
			button(inspector,str(row[0]),func() -> void:
				var next: Dictionary = data.duplicate(true)
				Model.find(next,selected_id)["params"].merge({"operation":"follow","follow":"Player","smoothing":row[1]},true)
				change("应用Camera2D预设",next))
	if kind == "tilemap":
		button(inspector,"选择瓦片…",func() -> void:
			var tiles: TileSet = load(node["params"]["tileset"]) as TileSet if not str(node["params"]["tileset"]).is_empty() else null
			var bound: Node = Access.node(target,str(node["params"]["target"])) if is_instance_valid(target) else null
			if tiles == null and bound is TileMapLayer: tiles = bound.tile_set
			if tiles == null: message.text = "请先选择TileSet或绑定已有图层"; return
			var picker: Window = TilePicker.new()
			add_child(picker)
			picker.connect("tile_selected",func(source: int,coords: Vector2i,alternative: int) -> void:
				var next: Dictionary = data.duplicate(true)
				Model.find(next,str(node["id"]))["params"].merge({"source":source,"atlas_x":coords.x,"atlas_y":coords.y,"alternative":alternative},true)
				change("选择瓦片",next))
			picker.call("present",tiles))
		button(inspector,"在原生TileMap／TileSet编辑器中打开",func() -> void:
			var bound: Node = Access.node(target,str(node["params"]["target"])) if is_instance_valid(target) else null
			if bound is TileMapLayer:
				EditorInterface.get_selection().clear()
				EditorInterface.get_selection().add_node(bound)
				EditorInterface.inspect_object(bound)
			elif not str(node["params"]["tileset"]).is_empty(): EditorInterface.edit_resource(load(node["params"]["tileset"]))
			else: message.text = "请先绑定场景图层或选择TileSet")


func field_group(kind: String, name: String, type: String, field: Array) -> String:
	if kind == "animation":
		if name in ["loops","reverse","pingpong","restore","wait","ui","policy","timeout"]: return "执行与恢复"
		if name in ["delay","seconds","transition","ease","speed"]: return "时长与缓动"
		if name in ["animation","frames","clip","player","remap","retarget"]: return "原生动画绑定"
	if kind == "button" and name in ["effects_enabled","hover_scale","pressed_scale","effect_seconds","click_animation"]: return "动画设置"
	if kind == "button" and (name in ["hover_sound", "click_sound", "volume", "bus"]):
		return "声音设置"
	if type == "asset":
		return "声音资源" if field[4] == "audio" else "脚本与子图" if field[4] in ["script", "module"] else "图像与资源"
	if type == "key":
		return "输入绑定"
	return "基础参数"


func parameter(field: String, value: Variant) -> void:
	if Model.find(data, selected_id)["params"].get(field) == value:
		return
	if field == "frames" and Model.find(data, selected_id)["kind"] == "runner" and not str(value).is_empty():
		bind_runner_frames(str(value))
		return
	var next: Dictionary = data.duplicate(true)
	var node: Dictionary = Model.find(next, selected_id)
	node["params"][field] = value
	if field == "value_type" and node["params"].has("json"):
		var initial: Variant = JSON.parse_string(str(node["params"]["json"]))
		if initial != null and not Model.Types.json_compatible(initial,str(value)): node["params"]["json"] = Model.Types.default_json(str(value))
	if node["kind"] == "animation" and field in ["frames","animation"] and not str(value).is_empty():
		node["params"]["mode"] = "frames" if field == "frames" else "animation"
		if field == "frames":
			var names: PackedStringArray = Drop.clips(Model.frames_at(str(value)))
			if not names.is_empty() and str(node["params"]["clip"]) not in names:
				node["params"]["clip"] = names[0]
		if is_instance_valid(target) and str(node["params"]["target"]).is_empty():
			var candidates: Array[Node] = target.find_children("*","AnimatedSprite2D" if field == "frames" else "AnimationPlayer",true,false)
			if candidates.size() == 1: node["params"]["target"] = str(target.get_path_to(candidates[0]))
	for definition: Array in Model.fields(str(node["kind"])):
		if definition[0] == field and definition[2] == "asset":
			if not node.has("resources"):
				node["resources"] = {}
			if str(value).is_empty():
				node["resources"].erase(field)
			else:
				node["resources"][field] = Link.descriptor(str(value))
	if not change("修改参数", next, field in ["value_type","mode","operation","use_from","effects_enabled","create_type","target","frames","animation"]):
		show_inspector()


func compatible_fields(id: String, path: String) -> Dictionary:
	var matches: Dictionary = {}
	var node: Dictionary = Model.find(data, id)
	if node.is_empty() or path.is_empty():
		return matches
	for field: Array in Model.fields(str(node["kind"])):
		if field[2] == "asset":
			var candidate: String = Drop.for_slot(path, str(field[4]))
			if Link.problem(candidate, str(field[4])).is_empty():
				matches[field[0]] = candidate
	return matches


func on_files_dropped(paths: PackedStringArray) -> void:
	if paths.size() != 1:
		return
	var id: String = Drop.node_at(graph, Vector2(DisplayServer.mouse_get_position()))
	if id.is_empty():
		return
	var path: String = Drop.project_file(paths[0])
	if path.is_empty():
		message.text = "请先在 AlI 为当前 Godot 项目准备组件。"
		return
	var drop_target: Node = target
	message.text = "正在导入素材…"
	if await Drop.import_files(self) and target == drop_target:
		bind_dropped_asset(id, path)


func bind_dropped_asset(id: String, path: String) -> void:
	var matches: Dictionary = compatible_fields(id, path)
	if matches.size() != 1:
		message.text = "这个模块没有匹配的素材槽。" if matches.is_empty() else "此模块有多个匹配素材槽，请拖到右侧对应的槽。"
		return
	selected_id = id
	var field: String = str(matches.keys()[0])
	var resource: String = matches[field]
	parameter(field, resource)
	show_inspector()


func bind_runner_frames(path: String) -> void:
	var runner: Dictionary = Model.find(data, selected_id)
	var params: Dictionary = runner["params"]
	var source: SpriteFrames = Model.frames_at(path)
	var names: PackedStringArray = Drop.clips(source)
	if names.is_empty():
		message.text = "组件没有可播放的动画帧。"
		return
	var clips: Dictionary = {}
	for field: String in ["walk", "jump", "death"]:
		if str(params[field]) in names:
			clips[field] = str(params[field])
		else:
			for name: String in names:
				if name == field or name.begins_with(field + "_") or (field == "walk" and (name == "run" or name.begins_with("run_"))):
					clips[field] = name
					break
	if clips.is_empty() and names.size() == 1:
		clips["walk"] = names[0]
	if clips.is_empty():
		message.text = "请选择包含行走／奔跑、跳跃或死亡动画的组件。"
		return
	var next: Dictionary = data.duplicate(true)
	var draft: Dictionary = Model.find(next, selected_id)
	if clips.size() == 3:
		for field: String in clips:
			draft["params"][field] = clips[field]
	else:
		var existing: SpriteFrames = Model.frames_at(str(params["frames"]))
		var merged: SpriteFrames = existing.duplicate() as SpriteFrames if existing != null else SpriteFrames.new()
		var fallback: String = str(clips.values()[0])
		for field: String in ["walk", "jump", "death"]:
			var name: String = str(params[field])
			if clips.has(field):
				Drop.copy_clip(merged, name, source, clips[field])
			elif not merged.has_animation(name) or merged.get_frame_count(name) == 0:
				Drop.copy_clip(merged, name, source, fallback, true)
		path = "res://generated/ali_assets/runner_frames_%s_%s.res" % [Time.get_ticks_usec(), randi()]
		var error: Error = DirAccess.make_dir_recursive_absolute(path.get_base_dir())
		if error == OK:
			error = ResourceSaver.save(merged, path)
		if error != OK:
			message.text = "无法保存绑定后的动画。"
			return
	draft["params"]["frames"] = path
	if not draft.has("resources"):
		draft["resources"] = {}
	draft["resources"]["frames"] = Link.descriptor(path)
	if change("绑定跑酷动画", next):
		message.text = "动画已绑定。请应用到游戏并保存场景。"
		if clips.size() < 3 and str(params["frames"]).is_empty():
			message.text += " 未提供的动作用静止帧占位，可继续拖入对应动画。"


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
	data = Link.normalize(stored)
	history.clear_history()
	target_label.text = "已绑定：" + str(target.name)
	render()


func apply_game() -> void:
	if not is_instance_valid(target):
		message.text = "请先绑定游戏根节点，或创建新场景。"
		return
	if not "compiled_blueprint" in target or not target.get_script() is GDScript or int(target.get_script().get_script_constant_map().get("API_VERSION", 0)) < 6:
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
	var only: CheckBox = CheckBox.new()
	only.text = "只显示收藏模块"
	only.toggled.connect(func(value: bool) -> void: favorites_only = value; filter_palette())
	box.add_child(only)
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
		if favorites_only and not kind in favorites: continue
		var label: String = ("★ " if kind in favorites else "")+Model.category(kind) + " · " + str(Model.TITLES[kind])
		if not term.is_empty() and not term in label.to_lower() and not term in kind:
			continue
		if kind in Model.SINGLETONS and not Model.by_kind(data, kind).is_empty():
			continue
		if not palette_source.is_empty():
			var compatible: bool = false
			for port: int in range(Model.INPUTS[kind].size()):
				if Model.port_type({"nodes":[Model.module("candidate", kind, 0, 0)]}, "candidate", port, false) == Model.port_type(data, palette_source, palette_port, true):
					compatible = true
			if not compatible:
				continue
		var index: int = results.add_item(label)
		results.set_item_metadata(index, kind)
		results.set_item_tooltip(index,EditorTools.description(kind))


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
			if Model.port_type({"nodes":[node]}, id, port, false) == Model.port_type(data, palette_source, palette_port, true):
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
	var parameterized: bool = false
	for id: String in selected:
		if Model.find(data,id)["kind"] in ["module_input","module_output"]: parameterized = true
	var result: Dictionary = ParameterLibrary.extract(data,selected,Library) if parameterized else Library.extract(data, selected)
	if result.has("error"):
		message.text = str(result["error"])
		return
	module_draft = result["data"]
	choose("save_module")


func show_debug() -> void:
	var dialog: AcceptDialog = AcceptDialog.new()
	dialog.title = "实时执行记录 · 点击定位源模块"
	debug_list = ItemList.new()
	debug_list.custom_minimum_size = Vector2(900,550)
	debug_list.item_selected.connect(func(index: int) -> void: focus_node(str(debug_list.get_item_metadata(index))))
	dialog.add_child(debug_list)
	add_child(dialog)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered()
	poll_debug()


func selected_nodes() -> Array[String]:
	var ids: Array[String] = []
	for child: Node in graph.get_children():
		if child is GraphNode and child.selected: ids.append(str(child.name))
	return ids


func copy_selected() -> void:
	var clipboard: Dictionary = EditorTools.copy(data,selected_nodes())
	if clipboard["nodes"].is_empty(): message.text = "请选择可复制的非核心模块"; return
	DisplayServer.clipboard_set(JSON.stringify(clipboard))
	message.text = "已复制%d个模块及内部连线" % clipboard["nodes"].size()


func paste_nodes() -> void:
	var clipboard: String = DisplayServer.clipboard_get()
	if clipboard.to_utf8_buffer().size() > 1024*1024: message.text = "剪贴板超过1MB"; return
	var result: Dictionary = EditorTools.paste(data,JSON.parse_string(clipboard))
	if result.has("error"): message.text = result["error"]; return
	if change("粘贴模块组",result["data"]):
		for child: Node in graph.get_children():
			if child is GraphNode: child.selected = str(child.name) in result["selected"]


func focus_node(id: String) -> void:
	var node: Dictionary = Model.find(data,id)
	if node.is_empty(): return
	selected_id = id
	show_inspector()
	graph.scroll_offset = Vector2(node["position"][0],node["position"][1])*graph.zoom-graph.size/2+Vector2(140,80)
	for child: Node in graph.get_children():
		if child is GraphNode: child.selected = str(child.name) == id


func poll_debug() -> void:
	if not visible: return
	var path: String = "user://ali_blueprint_"+str(Model.by_kind(data,"session")["params"]["save_key"])+".json"
	if not FileAccess.file_exists(path) or FileAccess.get_file_as_bytes(path).size() > 2*1024*1024: return
	var parser: JSON = JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK: return
	var snapshot: Variant = parser.data
	if not snapshot is Dictionary or snapshot.get("signature") != Library.signature(data): return
	debug_snapshot = snapshot
	if is_instance_valid(debug_list):
		debug_list.clear()
		for event: Dictionary in snapshot.get("events",[]):
			var index: int = debug_list.add_item(str(event.get("time",0))+"s · "+str(event.get("source",""))+" · "+str(event.get("detail","")))
			debug_list.set_item_metadata(index,str(event.get("source","")))
			if "失败" in str(event.get("detail","")) or "错误" in str(event.get("detail","")): debug_list.set_item_custom_fg_color(index,Color.SALMON)
	for widget: Node in graph.get_children():
		if not widget is GraphNode: continue
		var row: Dictionary = snapshot.get("nodes",{}).get(str(widget.name),{})
		if row.is_empty(): continue
		var status: String = str(row.get("state",""))
		var style: StyleBoxFlat = StyleBoxFlat.new()
		style.bg_color = Color("282d38")
		style.set_border_width_all(3)
		style.border_color = Color.SKY_BLUE if status == "running" else Color.MEDIUM_SEA_GREEN if status == "completed" else Color.SALMON if status == "failed" else Color.ORANGE
		widget.add_theme_stylebox_override("panel",style)
		widget.tooltip_text = EditorTools.description(str(Model.find(data,str(widget.name))["kind"]))+"\n"+status+" · "+str(row.get("detail",""))


func animation_clips(p: Dictionary) -> Array[String]:
	var result: Array[String] = []
	var resource: Resource = load(p["frames"]) if p["mode"] == "frames" and not str(p["frames"]).is_empty() else load(p["animation"]) if not str(p["animation"]).is_empty() else null
	var bound: Node = Access.node(target,str(p["target"])) if is_instance_valid(target) else null
	if resource == null and bound is AnimatedSprite2D: resource = bound.sprite_frames
	if resource is SpriteFrames:
		for clip: StringName in resource.get_animation_names(): result.append(str(clip))
	elif resource is AnimationLibrary:
		for clip: StringName in resource.get_animation_list(): result.append(str(clip))
	elif bound is AnimationPlayer:
		for clip: String in bound.get_animation_list(): result.append(clip)
	return result
