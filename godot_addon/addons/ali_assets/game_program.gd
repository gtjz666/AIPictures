extends RefCounted
## Pull-only data expressions and event-driven tasks; bounded, local to one game.
## Health/FSM invariants follow the skill's signal-driven component templates.
const Types: GDScript = preload("blueprint_types.gd")
const Access: GDScript = preload("blueprint_access.gd")
const Binding: GDScript = preload("animation_binding.gd")
const Model: GDScript = preload("game_model.gd")
var game: Node2D
var clock: float = 0.0
var values: Dictionary = {}
var flow: Dictionary = {}
var machines: Dictionary = {}
var health: Dictionary = {}
var messages: Dictionary = {}
var instances: Dictionary = {}
var bindings: Array[Dictionary] = []
var paused_modes: Dictionary = {}
var trace: Array[Dictionary] = []
var fault_count: int = 0
var cache: Dictionary = {}
var resetting: bool = false


func setup(controller: Node2D) -> void:
	game = controller
	reset(true)
	bind_signals()


func nodes() -> Array:
	return game.get("game_blueprint")["nodes"]


func record(id: String, detail: String) -> void:
	var node: Dictionary = Model.find(game.get("game_blueprint"), id)
	trace.append({"time": snappedf(clock, 0.001), "node": id, "source": node.get("_origin", id), "detail": detail.left(512)})
	if trace.size() > 256:
		trace.pop_front()


func fault(id: String, detail: String) -> void:
	fault_count += 1
	record(id, "错误：" + detail)
	if fault_count <= 8:
		push_warning("蓝图 " + id + "：" + detail)


func reset(initial: bool = false) -> void:
	resetting = true
	clock = 0.0
	cache.clear()
	flow.clear()
	messages.clear()
	machines.clear()
	health.clear()
	if not initial:
		for id: String in instances:
			clear_instances(id)
	for node: Dictionary in nodes():
		var id: String = str(node["id"])
		var p: Dictionary = node["params"]
		match str(node["kind"]):
			"blackboard":
				if p.get("scope","game") == "project":
					var global_values: Dictionary = game.get("services").get("globals")
					if not global_values.has(p["name"]) or not initial and p.get("reset_global",false): global_values[p["name"]] = Types.initial(p,game)
				elif initial or p["reset"]: game.get("variables")[p["name"]] = Types.initial(p, game)
			"boolean": game.get("variables")[p["name"]] = p["value"]
			"do_once": flow[id] = bool(p["closed"])
			"gate": flow[id] = bool(p["open"])
			"flip_flop": flow[id] = false
			"cooldown": flow[id] = -1.0
			"fsm": machines[p["name"]] = {"id": id, "current": str(p["initial"]), "previous": ""}
			"health": health[id] = {"value": float(p["initial"]), "immune_until": -1.0}
	resetting = false
	if not initial:
		for machine: Dictionary in machines.values():
			game.call("emit_port", str(machine["id"]), 0)


func tick(delta: float) -> void:
	clock += delta


func input_value(id: String, port: int, fallback: Variant, depth: int = 0) -> Variant:
	for edge: Dictionary in game.get("game_blueprint")["edges"]:
		if edge["to"] == id and int(edge["to_port"]) == port:
			return value(str(edge["from"]), int(edge["from_port"]), depth + 1)
	return fallback


func value(id: String, port: int, depth: int = 0) -> Variant:
	var key: String = id + ":" + str(port)
	if cache.has(key):
		return cache[key]
	if depth > 64:
		fault(id, "数据计算超过64层。")
		return 0.0
	var node: Dictionary = Model.find(game.get("game_blueprint"), id)
	var p: Dictionary = node["params"]
	var result: Variant = 0.0
	match str(node["kind"]):
		"blackboard", "boolean": result = game.get("services").get("globals").get(p["name"],Types.initial(p,game)) if p.get("scope","game") == "project" else game.get("variables").get(p["name"], false)
		"number", "text": result = p["value"]
		"math", "compare":
			var a: float = float(input_value(id, 0, p["a"], depth))
			var b: float = float(input_value(id, 1, p["b"], depth))
			match str(p["op"]):
				"add": result = a + b
				"subtract": result = a - b
				"multiply": result = a * b
				"divide":
					if is_zero_approx(b):
						fault(id, "除数为零，结果使用0。")
						result = 0.0
					else:
						result = a / b
				"min": result = minf(a, b)
				"max": result = maxf(a, b)
				"greater": result = a > b
				"less": result = a < b
				"equal": result = is_equal_approx(a, b)
				"greater_equal": result = a >= b
				"less_equal": result = a <= b
		"logic":
			var a: bool = bool(input_value(id, 0, p["a"], depth))
			var b: bool = bool(input_value(id, 1, p["b"], depth))
			result = not a if p["op"] == "not" else a and b if p["op"] == "and" else a or b
		"game_value": result = game.get_process_delta_time() if p["field"] == "delta" else game.get(str(p["field"]))
		"flip_flop": result = bool(flow.get(id, false))
		"fsm": result = messages.get(id + (":previous" if port == 3 else ":current"), machines[p["name"]]["previous" if port == 3 else "current"])
		"health": result = float(health[id]["value"]) / float(p["max"]) if port == 3 else float(health[id]["value"])
		"event_listener", "signal_event": result = messages.get(id, "")
		"format_text":
			var fallback: Variant = 0.0
			if p["value_type"] == "bool":
				fallback = false
			elif p["value_type"] == "text":
				fallback = ""
			result = str(p["template"]).replace("{value}", str(input_value(id, 0, fallback, depth)))
		_:
			if game.get("features") != null: result = game.get("features").call("value", node, port)
	if result is float and not is_finite(result):
		fault(id, "数字溢出，结果使用0。")
		result = 0.0
	cache[key] = result
	return result


func emit(id: String, port: int = 0) -> void:
	game.call("emit_port", id, port)


func execute(node: Dictionary, port: int) -> void:
	var id: String = str(node["id"])
	var p: Dictionary = node["params"]
	match str(node["kind"]):
		"set_variable":
			var next: Variant = input_value(id, 1, Types.initial(p, game))
			var valid: bool = Types.matches(next, str(p["value_type"]))
			var storage: Dictionary = game.get("services").get("globals") if p.get("scope","game") == "project" else game.get("variables")
			if not valid or not storage.has(p["name"]):
				fault(id, "变量缺失或值类型不一致。")
				return
			storage[p["name"]] = next
			emit(id)
		"do_once":
			if port == 1:
				flow[id] = false
			elif not flow[id]:
				flow[id] = true
				emit(id)
		"gate":
			if port > 0:
				flow[id] = not flow[id] if port == 3 else port == 1
			elif flow[id]:
				emit(id)
		"flip_flop":
			if port == 1:
				flow[id] = false
			else:
				flow[id] = not flow[id]
				emit(id, 0 if flow[id] else 1)
		"cooldown":
			if port == 1:
				flow[id] = -1.0
			elif clock >= float(flow[id]):
				flow[id] = clock + float(p["seconds"])
				emit(id)
			else:
				emit(id, 1)
		"fsm": switch_state(str(p["name"]), str(p["initial"]), true)
		"set_state": emit(id, 0 if switch_state(str(p["name"]), str(p["state"])) else 1)
		"event_emit":
			var text: String = str(input_value(id, 1, p["text"]))
			# Snapshot each delivery: a later event cannot replace an already queued payload.
			for listener: Dictionary in nodes():
				if listener["kind"] == "event_listener" and listener["params"]["name"] == p["name"]:
					game.call("queue_event", str(listener["id"]), text)
			emit(id)
		"health": change_health(id, p, port)
		"spawn_scene":
			if port == 1:
				clear_instances(id)
				return
			var live: Array = instances.get(id, [])
			live = live.filter(func(item: Node) -> bool: return is_instance_valid(item) and not item.is_queued_for_deletion())
			instances[id] = live
			if live.size() >= int(p["limit"]):
				emit(id, 1)
				return
			var packed: PackedScene = load(str(p["scene"])) as PackedScene
			var instance: Node = packed.instantiate()
			if not instance is Node2D:
				instance.free()
				fault(id, "场景实例需为Node2D或其子类。")
				emit(id, 1)
				return
			instance.name = str(p["name"])
			if instance is Node2D:
				(instance as Node2D).position = Vector2(float(input_value(id, 2, p["x"])), float(input_value(id, 3, p["y"])))
			var parent: Node = game.get("binding_root") as Node if "binding_root" in game else game
			parent.add_child(instance, true)
			live.append(instance)
			bind_signals()
			emit(id)
		"node_action": emit(id, 0 if node_action(p, id) else 1)
		"log":
			record(id, str(input_value(id, 1, p["text"])))
			emit(id)
		"ui_message":
			game.get("hud").call("show_message", str(input_value(id, 1, p["text"])), float(p["seconds"]))
			emit(id)


func switch_state(name: String, next: String, force: bool = false) -> bool:
	if not machines.has(name):
		return false
	var machine: Dictionary = machines[name]
	var p: Dictionary = Model.find(game.get("game_blueprint"), str(machine["id"]))["params"]
	if not next in str(p["states"]).split(","):
		return false
	var old: String = str(machine["current"])
	if old == next and not force:
		return true
	if not force and not str(p["transitions"]).is_empty() and not (old + ">" + next) in str(p["transitions"]).split(";"):
		return false
	machine["previous"] = old
	machine["current"] = next
	messages[str(machine["id"]) + ":previous"] = old
	messages[str(machine["id"]) + ":current"] = next
	record(str(machine["id"]), old + " → " + next)
	emit(str(machine["id"]), 2)
	emit(str(machine["id"]), 0)
	return true


func change_health(id: String, p: Dictionary, port: int) -> void:
	var data: Dictionary = health[id]
	var before: float = float(data["value"])
	var amount: float = maxf(0.0, float(input_value(id, 3, p["amount"])))
	if port == 2:
		data["value"] = float(p["initial"])
		data["immune_until"] = -1.0
	elif port == 0 and before > 0 and clock >= float(data["immune_until"]) and amount > 0:
		data["value"] = maxf(0.0, before - amount)
		data["immune_until"] = clock + float(p["invulnerability"])
	elif port == 1 and before > 0:
		data["value"] = minf(float(p["max"]), before + amount)
	if not is_equal_approx(before, float(data["value"])):
		emit(id)
		if before > 0 and float(data["value"]) <= 0:
			emit(id, 1)


func resolve(path: String) -> Node:
	return Access.node(game,path)


func node_action(p: Dictionary, id: String) -> bool:
	var target: Node = resolve(str(p["target"]))
	if not is_instance_valid(target) or target.is_queued_for_deletion():
		fault(id, "找不到目标：" + str(p["target"]))
		return false
	if p["op"] == "free" and (target in [game.get("actor"), game.get("world"), game.get("spawner"), game.get("hud")] or target in game.get("audio").values()):
		fault(id, "内建游戏模块请使用停止端口；删除操作用于自己的场景实例。")
		return false
	var xy: Vector2 = Vector2(float(input_value(id, 1, p["x"])), float(input_value(id, 2, p["y"])))
	match str(p["op"]):
		"show", "hide":
			if not target is CanvasItem:
				return false
			(target as CanvasItem).visible = p["op"] == "show"
		"enable", "disable": target.process_mode = Node.PROCESS_MODE_INHERIT if p["op"] == "enable" else Node.PROCESS_MODE_DISABLED
		"free": target.queue_free()
		"position", "translate":
			if not target is Node2D:
				return false
			(target as Node2D).position = xy if p["op"] == "position" else (target as Node2D).position + xy
		"velocity":
			if not target is CharacterBody2D:
				return false
			(target as CharacterBody2D).velocity = xy
		"animation":
			if target is AnimatedSprite2D and (target as AnimatedSprite2D).sprite_frames.has_animation(str(p["clip"])):
				Binding.play(target as AnimatedSprite2D,str(p["clip"]))
			elif target is AnimationPlayer and (target as AnimationPlayer).has_animation(str(p["clip"])):
				(target as AnimationPlayer).play(str(p["clip"]))
			else:
				return false
	return true


func clear_instances(id: String) -> void:
	for instance: Node in instances.get(id, []):
		if is_instance_valid(instance) and not instance.is_queued_for_deletion():
			instance.get_parent().remove_child(instance)
			instance.queue_free()
	instances[id] = []


func pause(active: bool) -> void:
	if active:
		for live: Array in instances.values():
			for instance: Node in live:
				if is_instance_valid(instance) and not paused_modes.has(instance):
					paused_modes[instance] = instance.process_mode
					instance.process_mode = Node.PROCESS_MODE_DISABLED
	else:
		for instance: Variant in paused_modes:
			if is_instance_valid(instance):
				instance.process_mode = paused_modes[instance]
		paused_modes.clear()


func bind_signals() -> void:
	bindings = bindings.filter(func(binding: Dictionary) -> bool: return is_instance_valid(binding["target"]))
	for node: Dictionary in nodes():
		if node["kind"] != "signal_event":
			continue
		var id: String = str(node["id"])
		var p: Dictionary = node["params"]
		var target: Node = resolve(str(p["target"]))
		if not is_instance_valid(target) or not target.has_signal(str(p["signal"])):
			continue
		var exists: bool = false
		for binding: Dictionary in bindings:
			if binding["target"] == target and binding["id"] == id:
				exists = true
		if exists:
			continue
		for signal_info: Dictionary in target.get_signal_list():
			if str(signal_info["name"]) != str(p["signal"]):
				continue
			var count: int = signal_info["args"].size()
			if count > 4:
				fault(id, "首版支持0到4参数的信号。")
				continue
			var callback: Callable = func(first: Variant) -> void: observed_signal(id, str(first))
			if count == 0:
				callback = func() -> void: observed_signal(id, "")
			elif count > 1:
				callback = callback.unbind(count - 1)
			if target.connect(str(p["signal"]), callback) == OK:
				bindings.append({"id": id, "target": target, "signal": str(p["signal"]), "callback": callback})


func observed_signal(id: String, payload: String) -> void:
	if not resetting and game.get("state") == "running":
		game.call("queue_event", id, payload)


func report() -> Dictionary:
	return {"version": 1, "state": game.get("state"), "variables": game.get("variables").duplicate(true), "machines": machines.duplicate(true), "health": health.duplicate(true), "faults": fault_count, "events": trace.duplicate(true)}


func dispose() -> void:
	for binding: Dictionary in bindings:
		if is_instance_valid(binding["target"]) and binding["target"].is_connected(binding["signal"], binding["callback"]):
			binding["target"].disconnect(binding["signal"], binding["callback"])
	bindings.clear()
	paused_modes.clear()
