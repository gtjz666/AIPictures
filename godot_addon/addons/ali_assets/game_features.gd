extends Node
## Generic 2D node adapters, separate from the legacy program and editor.
const Schema: GDScript = preload("extended_registry.gd")
const Types: GDScript = preload("blueprint_types.gd")
const Access: GDScript = preload("blueprint_access.gd")
const Task: GDScript = preload("blueprint_task.gd")
const Events: GDScript = preload("blueprint_events.gd")
var game: Node
var values: Dictionary = {}
var context: Dictionary = {}
var bindings: Array[Dictionary] = []
var bus: Node
var created_controls: Dictionary = {}


func setup(controller: Node) -> void:
	game = controller
	bus = Events.obtain(get_tree(), Events)
	bind_signals()
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] not in ["event_receive","game_event"]: continue
		var p: Dictionary = node["params"]
		var id: String = str(node["id"])
		var scope: String = event_scope(p) if node["kind"] == "event_receive" else project_scope()
		var event_name: String = str(p.get("name", p.get("event", "")))
		if node["kind"] == "game_event" and game.get("overlay_mode") == true and event_name in ["initialized", "scene_entered"]: continue
		bus.call("subscribe", self, scope, event_name, func(payload: Variant) -> void:
			if Types.matches(payload, str(p["value_type"])): game.call("queue_event", id, payload))


func initialize_overlay() -> void:
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] != "game_event": continue
		var p: Dictionary = node["params"]
		var payload: Dictionary = {"scene":game.get("binding_root").scene_file_path, "state":game.get("state")}
		if p["event"] in ["initialized", "scene_entered"] and Types.matches(payload, str(p["value_type"])):
			game.call("queue_event", str(node["id"]), payload)


func has_kind(kind: String) -> bool:
	return Schema.TITLES.has(kind)


func result(error: String = "", data: Variant = null) -> RefCounted:
	var task: RefCounted = Task.new()
	task.call("finish", "completed" if error.is_empty() else "failed", data, error)
	return task


func input(id: String, port: int, fallback: Variant) -> Variant:
	return game.get("program").call("input_value", id, port, fallback)


func target(p: Dictionary, id: String, port: int = 2) -> Node:
	return Access.node(game, input(id, port, p.get("target", "")))


func start(node: Dictionary, port: int, execution_context: Dictionary) -> RefCounted:
	context = execution_context
	game.get("program").set("messages", context.get("messages", {}))
	game.get("program").get("cache").clear()
	var id: String = str(node["id"])
	var kind: String = str(node["kind"])
	var p: Dictionary = node["params"].duplicate(true)
	if p.has("ui") and context.get("ui",false): p["ui"] = true
	var effective: Dictionary = node.duplicate(true)
	effective["params"] = p
	game.get("program").call("record", id, "执行输入 " + str(port))
	match kind:
		"animation":
			var subject: Node = Access.node(game, p["target"])
			if port > 0:
				game.get("animations").call("command", subject, "stop" if port == 1 else "pause" if port == 2 else "resume")
				return result()
			var task: RefCounted = game.get("animations").call("start", p) as RefCounted
			return task if p["wait"] else result()
		"ui_control", "property_set":
			var subject: Node = target(p, id)
			if subject == null and kind == "ui_control": subject = create_control(id,p)
			if subject == null: return result("找不到目标节点")
			var parameter_value: Variant = input(id, 1, Types.initial(p, game))
			if kind == "ui_control":
				if not subject is Control: return result("UI目标需要Control")
				if p["operation"] in ["show","hide","focus"]: return result(Access.invoke(subject, "grab_focus" if p["operation"] == "focus" else str(p["operation"]), []))
				var property: String = str({"color":"modulate","alpha":"modulate:a"}.get(p["operation"], p["operation"]))
				return result(Access.write(subject, property, parameter_value))
			return result(Access.write(subject, str(p["property"]), parameter_value))
		"method_call":
			var arguments: Variant = input(id, 1, JSON.parse_string(str(p["arguments"])))
			return result(Access.invoke(target(p, id), str(p["method"]), arguments)) if arguments is Array else result("方法参数必须为数组")
		"event_send":
			var payload: Variant = input(id, 1, Types.initial(p, game))
			if not Types.matches(payload, str(p["value_type"])): return result("事件参数类型不符")
			bus.call("send", event_scope(p), str(p["name"]), payload)
			return result()
		"module_output":
			context.get("returns", {})[p["name"]] = input(id, 1, Types.initial(p, game))
			return result()
		"camera2d", "background", "tilemap", "scene_object":
			if game.get("world_tools") != null: return game.get("world_tools").call("execute", effective, port, context) as RefCounted
		"input_bind", "audio_fx", "game_service", "scene_service", "settings_service", "save_service", "data_register", "subgraph":
			if game.get("services") != null: return game.get("services").call("execute", game, effective, port, context) as RefCounted
	return result("尚无此模块的运行适配器：" + kind)


func value(node: Dictionary, _port: int) -> Variant:
	var p: Dictionary = node["params"]
	var id: String = str(node["id"])
	match str(node["kind"]):
		"node_ref": return Access.node(game, p["target"])
		"frame_event": return game.get("program").get("messages").get(id, 0.0)
		"body_contact":
			var body: CharacterBody2D = target(p, id, 0) as CharacterBody2D
			if body == null: return false
			match p["surface"]:
				"wall": return body.is_on_wall()
				"ceiling": return body.is_on_ceiling()
				_: return body.is_on_floor()
		"resource_ref": return load(str(p["resource"])) if not str(p["resource"]).is_empty() else null
		"property_get": return Access.read(target(p, id, 0), str(p["property"]))
		"typed_value": return Types.initial(p, game)
		"event_receive", "ui_event", "game_event": return game.get("program").get("messages").get(id, Types.default_value(str(p["value_type"])))
		"module_input": return context.get("arguments", {}).get(p["name"], Types.initial(p, game))
		"collection":
			var data: Variant = input(id, 0, Types.from_json(str(p["json"]), str(p["container"]), game))
			if not data is Array and not data is Dictionary: return Types.default_value(str(p["value_type"]))
			if p["operation"] == "size": return float(data.size())
			var key: Variant = str(p["key"])
			if data is Array: key = int(p["key"])
			if p["operation"] == "get": return data[key] if data is Dictionary and data.has(key) or data is Array and int(key) >= 0 and int(key) < data.size() else Types.default_value(str(p["value_type"]))
			var copy: Variant = data.duplicate(true)
			var next: Variant = input(id, 1, Types.default_value(str(p["value_type"])))
			if p["operation"] == "append" and copy is Array: copy.append(next)
			elif p["operation"] == "erase":
				if copy is Dictionary: copy.erase(key)
				elif int(key) >= 0 and int(key) < copy.size(): copy.remove_at(int(key))
			elif p["operation"] == "set":
				if copy is Dictionary or int(key) >= 0 and int(key) < copy.size(): copy[key] = next
			return copy
		"input_action": return Input.get_action_strength(str(p["action"]))
	return context.get("values", {}).get(id, values.get(id, {}))


func bind_signals() -> void:
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] != "ui_event": continue
		var p: Dictionary = node["params"]
		var subject: Node = Access.node(game, p["target"])
		var id: String = str(node["id"])
		if subject == null or not subject.has_signal(str(p["signal"])): continue
		if bindings.any(func(row: Dictionary) -> bool: return row["target"] == subject and row["id"] == id): continue
		for signal_info: Dictionary in subject.get_signal_list():
			if str(signal_info["name"]) != str(p["signal"]): continue
			var count: int = signal_info["args"].size()
			var callback: Callable = func(payload: Variant) -> void: signal_received(id, p, payload)
			if count == 0: callback = func() -> void: signal_received(id, p, Types.default_value(str(p["value_type"])))
			elif count > 1: callback = callback.unbind(count - 1)
			subject.connect(str(p["signal"]), callback)
			bindings.append({"target":subject,"signal":str(p["signal"]),"callback":callback,"id":id})


func signal_received(id: String, p: Dictionary, payload: Variant) -> void:
	if game.get("state") == "paused" and not p["ui"]: return
	if Types.matches(payload, str(p["value_type"])): game.call("queue_event", id, payload)
	else: game.get("program").call("fault", id, "信号参数与所选类型不符")


func project_scope() -> String:
	return "project:" + (str(game.get("services").get("key")) if game.get("services") != null else str(game.call("settings", "session")["save_key"]))


func create_control(id: String, p: Dictionary) -> Control:
	if is_instance_valid(created_controls.get(id)): return created_controls[id] as Control
	var native: String = str(p.get("create_type","none"))
	if not native in ["Button","TextureButton","Label","RichTextLabel","TextureRect","Panel","PanelContainer","ProgressBar","HSlider","CheckBox","LineEdit","Control"]: return null
	var control: Control = ClassDB.instantiate(native) as Control
	control.name = str(p.get("name","Element"))
	var parent: Node = Access.node(game,p.get("parent",""))
	if parent == null: parent = game
	parent.add_child(control,true)
	control.custom_minimum_size = Vector2(float(p.get("width",200)),float(p.get("height",48)))
	if not parent is Container:
		control.position = Vector2(float(p.get("x",40)),float(p.get("y",40)))
		control.size = control.custom_minimum_size
	created_controls[id] = control
	bind_signals()
	return control


func event_scope(p: Dictionary) -> String:
	if p["scope"] == "project": return project_scope()
	if p["scope"] == "role":
		var actor: Node = Access.node(game, p["target"])
		return "role:" + str(actor.get_instance_id()) if actor != null else "missing-role"
	return "game:" + str(game.get_instance_id())


func _exit_tree() -> void:
	if is_instance_valid(bus): bus.call("unsubscribe", self)
	for row: Dictionary in bindings:
		if is_instance_valid(row["target"]) and row["target"].is_connected(row["signal"], row["callback"]): row["target"].disconnect(row["signal"], row["callback"])
	bindings.clear()
