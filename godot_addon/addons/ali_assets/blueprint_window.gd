@tool
extends Window

signal graph_applied(data: Dictionary)
const Model: GDScript = preload("blueprint_model.gd")
var data: Dictionary = Model.preset("two_way")
var graph: GraphEdit
var message: Label
var binding_label: Label
var target: Node
var frames: SpriteFrames
var history: UndoRedo = UndoRedo.new()
var capture_id: String = ""
var file_dialog: FileDialog
var file_operation: String = ""
var sound_id: String = ""
var settings_row: HBoxContainer
var dirty: bool = false


func _init() -> void:
	visible = false
	force_native = true


func _exit_tree() -> void:
	history.clear_history()
	history.free()


func _ready() -> void:
	title = "AlI · 角色蓝图工作台"
	min_size = Vector2i(900, 600)
	size = Vector2i(1280, 820)
	close_requested.connect(hide)
	window_input.connect(on_window_input)
	var root: VBoxContainer = VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(root)
	var toolbar: HBoxContainer = HBoxContainer.new()
	root.add_child(toolbar)
	var presets: MenuButton = MenuButton.new()
	presets.text = "新建预设 ▾"
	for title_text: String in ["双向移动角色", "四向移动角色", "平台跳跃角色"]:
		presets.get_popup().add_item(title_text)
	presets.get_popup().id_pressed.connect(func(index: int) -> void:
		change("新建预设", Model.preset(["two_way", "four_way", "platformer"][index], frames)))
	toolbar.add_child(presets)
	for entry: Array in [["按键", "key"], ["动作", "action"], ["动画", "animation"], ["音效", "sound"]]:
		var kind: String = str(entry[1])
		add_button(toolbar, "+ " + str(entry[0]), func() -> void: add_module(kind))
	var logic: MenuButton = MenuButton.new()
	logic.text = "+ 逻辑／自定义 ▾"
	for label: String in ["事件入口", "条件分支", "顺序执行", "延迟", "布尔变量", "自定义脚本模块"]:
		logic.get_popup().add_item(label)
	logic.get_popup().id_pressed.connect(func(index: int) -> void: add_module(["event", "branch", "sequence", "delay", "boolean", "custom"][index]))
	toolbar.add_child(logic)
	add_button(toolbar, "撤销", func() -> void: history.undo())
	add_button(toolbar, "重做", func() -> void: history.redo())
	add_button(toolbar, "打开…", func() -> void: choose_file("load"))
	add_button(toolbar, "保存蓝图…", func() -> void: choose_file("save"))
	add_button(toolbar, "应用到角色", apply_to_character)
	var binding: HBoxContainer = HBoxContainer.new()
	root.add_child(binding)
	var common: MenuButton = MenuButton.new()
	common.text = "常用功能组合 ▾"
	for label: String in ["攻击＋指定帧音效", "落地才能攻击", "按键延迟攻击"]:
		common.get_popup().add_item(label)
	common.get_popup().id_pressed.connect(add_common_module)
	binding.add_child(common)
	add_button(binding, "绑定当前选中角色", bind_selection)
	binding_label = Label.new()
	binding_label.text = "未绑定 · 可先搭建并保存蓝图；选中导出的角色根节点后绑定。"
	binding.add_child(binding_label)
	settings_row = HBoxContainer.new()
	root.add_child(settings_row)
	var hint: Label = Label.new()
	hint.text = "白色线：执行流程　绿色线：布尔条件　｜　拖动端口连线，右键端口断线；Delete删除。动作模块封装移动／跳跃／攻击等常用行为。"
	root.add_child(hint)
	graph = GraphEdit.new()
	graph.size_flags_vertical = Control.SIZE_EXPAND_FILL
	graph.right_disconnects = true
	graph.add_valid_connection_type(1, 2)
	graph.add_valid_connection_type(2, 3)
	graph.add_valid_connection_type(3, 4)
	graph.connection_request.connect(func(source: StringName, from_port: int, dest: StringName, to_port: int) -> void: connect_modules(str(source), str(dest), from_port, to_port))
	graph.disconnection_request.connect(func(source: StringName, from_port: int, dest: StringName, to_port: int) -> void: disconnect_modules(str(source), str(dest), from_port, to_port))
	graph.delete_nodes_request.connect(delete_modules)
	root.add_child(graph)
	message = Label.new()
	message.text = "蓝图只编排已有动作；攻击等模块会播放动画并发出动作信号。"
	root.add_child(message)
	file_dialog = FileDialog.new()
	file_dialog.access = FileDialog.ACCESS_RESOURCES
	file_dialog.force_native = true
	file_dialog.file_selected.connect(on_file_selected)
	add_child(file_dialog)
	render()


func add_button(parent: Node, text: String, callback: Callable) -> Button:
	var button: Button = Button.new()
	button.text = text
	button.pressed.connect(callback)
	parent.add_child(button)
	return button


func change(label: String, next: Dictionary) -> bool:
	var problem: String = Model.validate(next)
	if not problem.is_empty():
		message.text = problem
		return false
	if data == next:
		return true
	history.create_action(label)
	history.add_do_method(set_data.bind(next.duplicate(true)))
	history.add_undo_method(set_data.bind(data.duplicate(true)))
	history.commit_action()
	return true


func set_data(next: Dictionary) -> void:
	data = next.duplicate(true)
	dirty = true
	capture_id = ""
	render()
	message.text = "蓝图已修改；应用到角色后请保存场景，或单独保存蓝图。"


func bind_selection() -> void:
	var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
	if selected.size() != 1:
		message.text = "请选中一个导出的角色根节点。"
		return
	bind_character(selected[0])


func bind_character(character: Node) -> bool:
	if not is_instance_valid(character) or not "blueprint" in character or not character.has_node("AnimatedSprite2D"):
		message.text = "请选择新版导出的双向、四向或平台角色根节点。"
		return false
	if dirty and is_instance_valid(target) and target != character:
		message.text = "请先应用或保存当前修改，再使用“打开”载入另一份蓝图。"
		return false
	target = character
	frames = (target.get_node("AnimatedSprite2D") as AnimatedSprite2D).sprite_frames
	binding_label.text = "已绑定：" + str(target.name)
	if not dirty:
		var stored: Dictionary = target.get("blueprint")
		var mode: String = "platformer" if target.get("platformer") else "four_way" if target.get("four_way") else "two_way"
		if stored.is_empty():
			var keys: Dictionary = {}
			for action: String in ["move_left", "move_right", "move_up", "move_down", "run", "jump", "attack"]:
				keys[action] = target.get("key_" + action.trim_prefix("move_"))
			data = Model.preset(mode, frames, keys)
			for property: String in ["speed", "run_multiplier", "gravity", "jump_velocity"]:
				data["settings"][property] = target.get(property)
		else:
			var problem: String = Model.validate(stored)
			if not problem.is_empty():
				message.text = problem
				return false
			data = stored.duplicate(true)
		history.clear_history()
	render()
	message.text = "已读取角色动画。连接完成后点击“应用到角色”，再保存场景。"
	return true


func apply_to_character() -> void:
	if not is_instance_valid(target):
		message.text = "请先选中并绑定导出的角色根节点。"
		return
	var problem: String = Model.validate(data, frames)
	if not problem.is_empty():
		message.text = problem
		return
	graph_applied.emit(data.duplicate(true))
	dirty = false
	message.text = "已应用到角色。请保存场景；运行时将按连线触发动画与音效。"


func add_module(kind: String) -> void:
	var next: Dictionary = data.duplicate(true)
	var id: String = "n_" + str(Time.get_ticks_usec())
	var params: Dictionary = {}
	match kind:
		"key": params = {"code": KEY_F}
		"action":
			for action: String in Model.ACTIONS:
				var used: bool = false
				for node: Dictionary in next["nodes"]:
					if node["kind"] == "action" and node["params"]["action"] == action:
						used = true
				if not used:
					params = {"action": action}
					break
			if params.is_empty():
				message.text = "所有动作模块都已添加。"
				return
		"animation": params = {"clip": str(frames.get_animation_names()[0]) if frames != null and not frames.get_animation_names().is_empty() else "walk_right"}
		"sound": params = {"path": "", "trigger": "start", "frame": 0, "interval": 0.35, "volume": 0.0}
		"event": params = {"event": "ready"}
		"branch": params = {"condition": "grounded", "invert": false}
		"sequence": params = {}
		"delay": params = {"seconds": 0.5}
		"boolean": params = {"name": "can_act_" + str(Time.get_ticks_usec()), "value": true}
		"custom": params = {"script": ""}
	var offset: Vector2 = graph.scroll_offset + Vector2(100, 100) / graph.zoom
	next["nodes"].append(Model.make_node(id, kind, offset.x, offset.y, params))
	change("添加模块", next)


func update_parameter(id: String, field: String, value: Variant) -> void:
	var next: Dictionary = data.duplicate(true)
	Model.find_node(next, id)["params"][field] = value
	change("修改模块", next)


func add_choice(parent: Node, options: Dictionary, selected: String, callback: Callable) -> void:
	var choice: OptionButton = OptionButton.new()
	var keys: Array = options.keys()
	for key: String in keys:
		choice.add_item(str(options[key]))
	choice.selected = keys.find(selected)
	choice.item_selected.connect(func(index: int) -> void: callback.call(str(keys[index])))
	parent.add_child(choice)


func add_common_module(index: int) -> void:
	# Editable prefabs use the same runtime nodes as user graphs.
	var next: Dictionary = data.duplicate(true)
	var prefix: String = "module_" + str(Time.get_ticks_usec())
	var aid: String = ""
	for node: Dictionary in next["nodes"]:
		if node["kind"] == "action" and node["params"]["action"] == "attack":
			aid = str(node["id"])
	if aid.is_empty():
		aid = prefix + "_action"
		next["nodes"].append(Model.make_node(aid, "action", 600, 100, {"action": "attack"}))
	var kid: String = prefix + "_key"
	next["nodes"].append(Model.make_node(kid, "key", 0, 100, {"code": KEY_J}))
	var anim: String = ""
	for node: Dictionary in Model.outgoing(next, aid):
		anim = str(node["id"])
	if anim.is_empty():
		anim = prefix + "_animation"
		var clip: String = "attack" if frames != null and frames.has_animation("attack") else "attack_right"
		next["nodes"].append(Model.make_node(anim, "animation", 900, 100, {"clip": clip}))
		next["edges"].append({"from": aid, "to": anim})
	if index == 0:
		next["edges"].append({"from": kid, "to": aid, "from_port": 1})
		var sid: String = prefix + "_sound"
		next["nodes"].append(Model.make_node(sid, "sound", 1200, 100, {"path": "", "trigger": "frame", "frame": 0, "interval": 0.35, "volume": 0.0}))
		next["edges"].append({"from": anim, "to": sid})
	else:
		var logic: String = prefix + "_logic"
		var params: Dictionary = {"condition": "grounded", "invert": false} if index == 1 else {"seconds": 0.5}
		next["nodes"].append(Model.make_node(logic, "branch" if index == 1 else "delay", 300, 100, params))
		next["edges"] = next["edges"].filter(func(edge: Dictionary) -> bool: return edge["to"] != aid or Model.find_node(next, str(edge["from"]))["kind"] != "key")
		next["edges"].append({"from": kid, "to": logic, "from_port": 1})
		next["edges"].append({"from": logic, "to": aid})
	change("加入常用功能模块", next)


func connect_modules(source: String, dest: String, from_port: int = 0, to_port: int = 0) -> bool:
	var next: Dictionary = data.duplicate(true)
	next["edges"].append({"from": source, "to": dest, "from_port": from_port, "to_port": to_port})
	return change("连接模块", next)


func disconnect_modules(source: String, dest: String, from_port: int = 0, to_port: int = 0) -> void:
	var next: Dictionary = data.duplicate(true)
	next["edges"] = next["edges"].filter(func(edge: Dictionary) -> bool: return edge["from"] != source or edge["to"] != dest or int(edge.get("from_port", 0)) != from_port or int(edge.get("to_port", 0)) != to_port)
	change("断开连线", next)


func delete_modules(ids: Array[StringName]) -> void:
	var next: Dictionary = data.duplicate(true)
	next["nodes"] = next["nodes"].filter(func(node: Dictionary) -> bool: return not StringName(node["id"]) in ids)
	next["edges"] = next["edges"].filter(func(edge: Dictionary) -> bool: return not StringName(edge["from"]) in ids and not StringName(edge["to"]) in ids)
	change("删除模块", next)


func render() -> void:
	if graph == null:
		return
	graph.clear_connections()
	for child: Node in graph.get_children():
		if child is GraphNode:
			graph.remove_child(child)
			child.queue_free()
	for node: Dictionary in data["nodes"]:
		render_node(node)
	for edge: Dictionary in data["edges"]:
		graph.connect_node(str(edge["from"]), int(edge.get("from_port", 0)), str(edge["to"]), int(edge.get("to_port", 0)))
	for child: Node in settings_row.get_children():
		settings_row.remove_child(child)
		child.queue_free()
	var mode: OptionButton = OptionButton.new()
	for label: String in ["双向移动", "四向移动", "平台跳跃"]:
		mode.add_item(label)
	mode.selected = ["two_way", "four_way", "platformer"].find(data["settings"]["mode"])
	mode.item_selected.connect(func(index: int) -> void: update_setting("mode", ["two_way", "four_way", "platformer"][index]))
	settings_row.add_child(mode)
	for entry: Array in [["速度", "speed", 1, 2000], ["奔跑倍率", "run_multiplier", 1, 5], ["重力", "gravity", 0, 10000], ["跳跃速度", "jump_velocity", -3000, -1]]:
		var field: String = str(entry[1])
		var label: Label = Label.new()
		label.text = str(entry[0])
		settings_row.add_child(label)
		var spin: SpinBox = SpinBox.new()
		spin.min_value = float(entry[2])
		spin.max_value = float(entry[3])
		spin.step = 0.1 if field == "run_multiplier" else 1.0
		spin.value = float(data["settings"][field])
		spin.value_changed.connect(func(value: float) -> void: update_setting(field, value))
		settings_row.add_child(spin)


func update_setting(field: String, value: Variant) -> void:
	var next: Dictionary = data.duplicate(true)
	next["settings"][field] = value
	change("修改运动参数", next)


func render_node(node: Dictionary) -> void:
	var widget: GraphNode = GraphNode.new()
	var id: String = str(node["id"])
	var kind: String = str(node["kind"])
	var params: Dictionary = node["params"]
	widget.name = id
	widget.title = {"key": "按键事件", "action": "封装动作模块", "animation": "播放动画", "sound": "播放音效", "event": "事件入口", "branch": "条件分支", "sequence": "顺序执行", "delay": "延迟", "boolean": "布尔变量", "custom": "自定义模块"}[kind]
	widget.custom_minimum_size = Vector2(240, 0)
	var bar: StyleBoxFlat = StyleBoxFlat.new()
	bar.bg_color = Color("803b43") if kind in ["key", "event"] else Color("36617e") if kind in ["action", "animation"] else Color("655084") if kind == "custom" else Color("447459") if kind == "boolean" else Color("585858")
	bar.content_margin_left = 10
	bar.content_margin_right = 10
	bar.content_margin_top = 6
	bar.content_margin_bottom = 6
	widget.add_theme_stylebox_override("titlebar", bar)
	var selected_bar: StyleBoxFlat = bar.duplicate() as StyleBoxFlat
	selected_bar.bg_color = bar.bg_color.lightened(0.2)
	widget.add_theme_stylebox_override("titlebar_selected", selected_bar)
	widget.position_offset = Vector2(float(node["position"][0]), float(node["position"][1]))
	graph.add_child(widget)
	var port: Label = Label.new()
	port.text = {"key": "按住时 →", "action": "执行 → 动画", "animation": "执行 → 动画时刻", "sound": "执行音效", "event": "事件发生时 →", "branch": "执行 → 成立", "sequence": "执行 → 先执行1", "delay": "执行 → 等待后", "boolean": "布尔值 →", "custom": "执行 → 完成"}[kind]
	widget.add_child(port)
	widget.set_slot(0, kind not in ["key", "event", "boolean"], 0, Color.WHITE, kind != "sound", 6 if kind == "boolean" else 0, Color.MEDIUM_SEA_GREEN if kind == "boolean" else Color.WHITE)
	if kind in ["key", "branch", "sequence", "custom"]:
		var second: Label = Label.new()
		second.text = {"key": "按下时 →（仅一次）", "branch": "布尔条件 → 不成立", "sequence": "再执行2 →", "custom": "备用 →"}[kind]
		widget.add_child(second)
		widget.set_slot(1, kind == "branch", 6, Color.MEDIUM_SEA_GREEN, true, 0, Color.WHITE)
	widget.dragged.connect(func(_from: Vector2, to: Vector2) -> void:
		var next: Dictionary = data.duplicate(true)
		Model.find_node(next, id)["position"] = [to.x, to.y]
		change("移动模块", next))
	match kind:
		"event":
			add_choice(widget, Model.EVENTS, str(params["event"]), func(value: String) -> void: update_parameter(id, "event", value))
		"branch":
			add_choice(widget, Model.CONDITIONS, str(params["condition"]), func(value: String) -> void: update_parameter(id, "condition", value))
			var hint: Label = Label.new()
			hint.text = "连接绿色输入时，改用布尔变量判断。"
			widget.add_child(hint)
			var invert: CheckBox = CheckBox.new()
			invert.text = "条件取反"
			invert.button_pressed = bool(params["invert"])
			invert.toggled.connect(func(value: bool) -> void: update_parameter(id, "invert", value))
			widget.add_child(invert)
		"delay":
			var spin: SpinBox = SpinBox.new()
			spin.min_value = 0.01
			spin.max_value = 60
			spin.step = 0.01
			spin.suffix = "秒"
			spin.value = float(params["seconds"])
			spin.value_changed.connect(func(value: float) -> void: update_parameter(id, "seconds", value))
			widget.add_child(spin)
		"boolean":
			var edit: LineEdit = LineEdit.new()
			edit.text = str(params["name"])
			edit.text_submitted.connect(func(value: String) -> void: update_parameter(id, "name", value.strip_edges()))
			widget.add_child(edit)
			var value: CheckBox = CheckBox.new()
			value.text = "初始值：真"
			value.button_pressed = bool(params["value"])
			value.toggled.connect(func(on: bool) -> void: update_parameter(id, "value", on))
			widget.add_child(value)
		"custom":
			var path: String = str(params["script"])
			add_button(widget, path.get_file() if not path.is_empty() else "选择模块脚本…", func() -> void:
				sound_id = id
				choose_file("script"))
			add_button(widget, "新建可编写模块…", func() -> void:
				sound_id = id
				choose_file("new_module"))
			if not path.is_empty():
				add_button(widget, "在Godot中编辑脚本", func() -> void: EditorInterface.edit_script(load(path) as Script))
		"key":
			add_button(widget, OS.get_keycode_string(int(params["code"])) + " · 点击改键", func() -> void:
				capture_id = id
				message.text = "请按新键（Esc取消），物理键位不受输入法影响。")
		"action":
			var option: OptionButton = OptionButton.new()
			var keys: Array = Model.ACTIONS.keys()
			for action: String in keys:
				option.add_item(str(Model.ACTIONS[action]))
			option.selected = keys.find(params["action"])
			option.item_selected.connect(func(index: int) -> void: update_parameter(id, "action", keys[index]))
			widget.add_child(option)
			var hint: Label = Label.new()
			hint.text = "移动／奔跑为按住；其他动作为按下触发。\n跳跃物理仅对平台模式生效。"
			widget.add_child(hint)
		"animation":
			if frames != null:
				var option: OptionButton = OptionButton.new()
				var clips: PackedStringArray = frames.get_animation_names()
				for clip: String in clips:
					option.add_item(clip)
				if not str(params["clip"]) in clips:
					clips.append(str(params["clip"]))
					option.add_item(str(params["clip"]) + "（缺少动画）")
				option.selected = clips.find(str(params["clip"]))
				option.item_selected.connect(func(index: int) -> void: update_parameter(id, "clip", clips[index]))
				widget.add_child(option)
			else:
				var edit: LineEdit = LineEdit.new()
				edit.text = str(params["clip"])
				edit.placeholder_text = "动画名称，回车确认"
				edit.text_submitted.connect(func(text: String) -> void: update_parameter(id, "clip", text.strip_edges()))
				widget.add_child(edit)
		"sound":
			var path: String = str(params["path"])
			var button: Button = add_button(widget, path.get_file() if not path.is_empty() else "选择项目音效…", func() -> void:
				sound_id = id
				choose_file("sound"))
			button.tooltip_text = path
			var trigger: OptionButton = OptionButton.new()
			for label: String in ["动画开始时", "指定动画帧（从0开始）", "动画播放中按间隔重复"]:
				trigger.add_item(label)
			trigger.selected = ["start", "frame", "repeat"].find(params["trigger"])
			trigger.item_selected.connect(func(index: int) -> void: update_parameter(id, "trigger", ["start", "frame", "repeat"][index]))
			widget.add_child(trigger)
			for entry: Array in [["触发帧", "frame", 0, 100000, 1], ["间隔／秒", "interval", 0.05, 60, 0.05], ["音量／dB", "volume", -60, 6, 1]]:
				var field: String = str(entry[1])
				var row: HBoxContainer = HBoxContainer.new()
				var label: Label = Label.new()
				label.text = str(entry[0])
				row.add_child(label)
				var spin: SpinBox = SpinBox.new()
				spin.min_value = float(entry[2])
				spin.max_value = float(entry[3])
				spin.step = float(entry[4])
				spin.value = float(params[field])
				spin.editable = field == "volume" or (field == "frame" and params["trigger"] == "frame") or (field == "interval" and params["trigger"] == "repeat")
				spin.value_changed.connect(func(value: float) -> void: update_parameter(id, field, value))
				row.add_child(spin)
				widget.add_child(row)


func on_window_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	if not capture_id.is_empty():
		if event.keycode != KEY_ESCAPE:
			update_parameter(capture_id, "code", event.physical_keycode if event.physical_keycode != 0 else event.keycode)
		capture_id = ""
		get_viewport().set_input_as_handled()
	elif event.ctrl_pressed and event.keycode == KEY_Z:
		history.redo() if event.shift_pressed else history.undo()
		get_viewport().set_input_as_handled()


func choose_file(operation: String) -> void:
	file_operation = operation
	file_dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE if operation in ["save", "new_module"] else FileDialog.FILE_MODE_OPEN_FILE
	file_dialog.filters = PackedStringArray(["*.wav,*.ogg,*.mp3 ; 音效"]) if operation == "sound" else PackedStringArray(["*.gd ; 自定义模块"]) if operation in ["script", "new_module"] else PackedStringArray(["*.json ; AlI角色蓝图"])
	file_dialog.title = {"save": "保存角色蓝图", "load": "打开角色蓝图", "sound": "选择项目内音效", "script": "选择自定义脚本模块", "new_module": "新建自定义脚本模块"}[operation]
	if operation == "save":
		file_dialog.current_file = "character_blueprint.json"
	elif operation == "new_module":
		file_dialog.current_file = "custom_module.gd"
	file_dialog.popup_centered(Vector2i(800, 540))


func on_file_selected(path: String) -> void:
	if not path.begins_with("res://") or ".." in path:
		message.text = "请选择当前项目内的文件。"
		return
	if file_operation == "sound":
		update_parameter(sound_id, "path", path)
	elif file_operation in ["script", "new_module"]:
		if path.get_extension() != "gd":
			message.text = "请选择.gd模块脚本。"
			return
		if file_operation == "new_module":
			if FileAccess.file_exists(path):
				message.text = "此文件已存在，请选择新名称以保留原脚本。"
				return
			var template: String = FileAccess.get_file_as_string(get_script().resource_path.get_base_dir().path_join("custom_module_template.gd"))
			var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
			if file == null:
				message.text = "模块保存失败。"
				return
			file.store_string(template)
			file.close()
		update_parameter(sound_id, "script", path)
		EditorInterface.get_resource_filesystem().scan()
		EditorInterface.edit_script(load(path) as Script)
	elif file_operation == "save":
		if path.get_extension().to_lower() != "json":
			path += ".json"
		var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
		if file == null:
			message.text = "蓝图保存失败，请检查位置是否可写。"
			return
		file.store_string(JSON.stringify(data, "\t"))
		file.close()
		dirty = false
		message.text = "已保存：" + path + "；应用到角色后仍需保存场景。"
	else:
		if FileAccess.get_file_as_bytes(path).size() > 1024 * 1024:
			message.text = "蓝图文件过大。"
			return
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if not parsed is Dictionary:
			message.text = "这不是有效的蓝图文件。"
			return
		change("打开蓝图", parsed)
