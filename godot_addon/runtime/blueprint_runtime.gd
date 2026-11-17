extends RefCounted
## Installed beside the generated player; no editor plugin needed at runtime.
const Types: GDScript = preload("blueprint_types.gd")
const Events: GDScript = preload("blueprint_events.gd")
const Binding: GDScript = preload("animation_binding.gd")
var bus: Node
var payload: Variant
var event_values: Dictionary = {}
const Model: GDScript = preload("blueprint_model.gd")
const Link: GDScript = preload("resource_link.gd")
var data: Dictionary = {}
var sprite: AnimatedSprite2D
var players: Dictionary = {}
var elapsed: Dictionary = {}
var held: Dictionary = {}
var active_animation: String = ""
var last_frame: int = -1
var error: String = ""
var actor: CharacterBody2D
var key_held: Dictionary = {}
var requests: Dictionary = {}
var pending: Array[Dictionary] = []
var modules: Dictionary = {}
var variables: Dictionary = {}
var frame_delta: float = 0.0
var previous_floor: bool = false
var execution_budget: int = 512


func setup(graph: Dictionary, owner_node: Node, animated: AnimatedSprite2D) -> bool:
	graph = Link.normalize(graph)
	error = Model.validate(graph, animated.sprite_frames)
	if not error.is_empty():
		return false
	for node: Dictionary in graph["nodes"]:
		error = Link.metadata_problem(node)
		if not error.is_empty():
			return false
	data = graph.duplicate(true)
	sprite = animated
	actor = owner_node as CharacterBody2D
	for node: Dictionary in data["nodes"]:
		if node["kind"] == "boolean":
			variables[str(node["params"]["name"])] = node["params"]["value"]
		if node["kind"] == "custom":
			var script: GDScript = load(str(node["params"]["script"])) as GDScript
			if script == null or script.get_instance_base_type() != &"RefCounted":
				error = "自定义模块必须继承RefCounted。"
				return false
			var instance: RefCounted = script.new() as RefCounted
			if instance == null or not instance.has_method("execute"):
				error = "自定义模块缺少execute(context)方法。"
				return false
			modules[node["id"]] = instance
		if node["kind"] != "sound" or str(node["params"]["path"]).is_empty():
			continue
		var stream: AudioStream = load(str(node["params"]["path"])) as AudioStream
		if stream == null:
			continue
		var player: AudioStreamPlayer2D = AudioStreamPlayer2D.new()
		player.name = "BlueprintSound_" + str(node["id"])
		player.stream = stream
		player.volume_db = float(node["params"]["volume"])
		owner_node.add_child(player)
		players[node["id"]] = player
	sprite.frame_changed.connect(on_frame)
	sprite.animation_finished.connect(func() -> void: emit_event("animation_finished"))
	bus = Events.obtain(actor.get_tree(),Events)
	for node: Dictionary in data["nodes"]:
		if node["kind"] == "receive_event":
			var p: Dictionary = node["params"]
			var id: String = str(node["id"])
			bus.call("subscribe",actor,event_scope(str(p["scope"])),str(p["name"]),func(value: Variant) -> void:
				if Types.matches(value,str(p["value_type"])):
					payload = value
					event_values[id] = value
					execution_budget = 512
					follow(id,0,requests,true,0))
	return true


func input_state(delta: float = 0.0) -> Dictionary:
	execution_budget = 512
	frame_delta = delta
	if actor.is_on_floor() and not previous_floor:
		emit_event("land")
	previous_floor = actor.is_on_floor()
	var active: Dictionary = requests.duplicate()
	requests.clear()
	var due: Array[Dictionary] = pending
	pending = []
	for item: Dictionary in due:
		item["remaining"] = float(item["remaining"]) - delta
		if float(item["remaining"]) <= 0.0:
			payload = item.get("payload")
			event_values = item.get("event_values",{})
			follow(str(item["source"]), 0, active, true, 0)
		else:
			pending.append(item)
	var pressed: Array[String] = []
	var now: Dictionary = {}
	for node: Dictionary in data.get("nodes", []):
		if node["kind"] != "key": continue
		var action: String = str(node["params"].get("input_action", ""))
		var down: bool = Input.is_action_pressed(action) if not action.is_empty() and InputMap.has_action(action) else Input.is_physical_key_pressed(int(node["params"]["code"]))
		if not down or actor.get_viewport().gui_get_focus_owner() is LineEdit or actor.get_viewport().gui_get_focus_owner() is TextEdit:
			continue
		var id: String = str(node["id"])
		now[id] = true
		var pulse: bool = not key_held.has(id)
		follow(id, 0, active, pulse, 0)
		if pulse:
			follow(id, 1, active, true, 0)
	key_held = now
	for action: String in active:
		if not held.has(action):
			pressed.append(action)
	held = active
	return {"active": active, "pressed": pressed, "direction": Vector2(
		float(active.has("move_right")) - float(active.has("move_left")),
		float(active.has("move_down")) - float(active.has("move_up")))}


func emit_event(event: String) -> void:
	for node: Dictionary in data.get("nodes", []):
		if node["kind"] == "event" and node["params"]["event"] == event:
			follow(str(node["id"]), 0, requests, true, 0)


func follow(source: String, port: int, active: Dictionary, pulse: bool, depth: int) -> void:
	if depth > 64 or execution_budget <= 0:
		return
	execution_budget -= 1
	for edge: Dictionary in data.get("edges", []):
		if edge["from"] != source or int(edge.get("from_port", 0)) != port or int(edge.get("to_port", 0)) != 0:
			continue
		var node: Dictionary = Model.find_node(data, str(edge["to"]))
		var id: String = str(node["id"])
		var params: Dictionary = node["params"]
		match str(node["kind"]):
			"send_event":
				if pulse:
					var value: Variant = data_input(id,1,Types.initial(params,actor))
					if Types.matches(value,str(params["value_type"])): bus.call("send",event_scope(str(params["scope"])),str(params["name"]),value)
					follow(id,0,active,true,depth+1)
			"action": active[str(params["action"])] = true
			"branch": follow(id, 0 if condition(node) else 1, active, pulse, depth + 1)
			"sequence":
				follow(id, 0, active, pulse, depth + 1)
				follow(id, 1, active, pulse, depth + 1)
			"delay":
				if pulse and pending.size() < 128:
					pending.append({"source": id, "remaining": float(params["seconds"]),"payload":payload,"event_values":event_values.duplicate(true)})
			"custom":
				if pulse and modules.has(id):
					var result: Variant = (modules[id] as RefCounted).call("execute", {"actor": actor, "delta": frame_delta, "variables": variables,"payload":payload})
					if result is Dictionary:
						follow(id, clampi(int(result.get("output", 0)), 0, 1), active, true, depth + 1)
			"animation":
				if pulse:
					if play_animation(node, true):
						actor.set("action_time", actor.call("animation_duration"))
			"sound":
				# Animation outputs are handled by their start/frame/repeat policy.
				if pulse and Model.find_node(data, source)["kind"] != "animation":
					play_sound(id)


func condition(node: Dictionary) -> bool:
	var params: Dictionary = node["params"]
	var value: bool = false
	match str(params["condition"]):
		"grounded": value = actor.is_on_floor()
		"in_air": value = not actor.is_on_floor()
		"moving": value = actor.velocity.length_squared() > 1.0
		"running": value = bool(actor.get("is_running"))
		"always": value = true
	for edge: Dictionary in data["edges"]:
		if edge["to"] == node["id"] and int(edge.get("to_port", 0)) == 1:
			value = bool(data_input(str(node["id"]),1,false))
	return not value if params["invert"] else value


func play(action: String, restart: bool = false) -> bool:
	for node: Dictionary in data.get("nodes", []):
		if node["kind"] != "action" or str(node["params"]["action"]) != action:
			continue
		var animations: Array[Dictionary] = Model.outgoing(data, str(node["id"]))
		if animations.is_empty():
			return false
		var animation: Dictionary = animations[0]
		return play_animation(animation, restart)
	return false


func play_animation(animation: Dictionary, restart: bool = false) -> bool:
	var clip: String = str(animation["params"]["clip"])
	if not sprite.sprite_frames.has_animation(clip):
		return false
	var changed: bool = active_animation != str(animation["id"]) or sprite.animation != StringName(clip) or restart
	if changed:
		stop_repeats()
		active_animation = str(animation["id"])
		last_frame = -1
		if restart:
			sprite.stop()
		Binding.play(sprite,clip)
		for sound: Dictionary in Model.outgoing(data, active_animation):
			if sound["kind"] != "sound":
				continue
			elapsed[sound["id"]] = 0.0
			if sound["params"]["trigger"] in ["start", "repeat"]:
				play_sound(str(sound["id"]))
		on_frame()
		# Flow controllers after an animation start can schedule further work.
		for edge: Dictionary in data["edges"]:
			if edge["from"] == active_animation and Model.find_node(data, str(edge["to"]))["kind"] != "sound":
				follow(active_animation, 0, requests, true, 0)
				break
	elif not sprite.is_playing():
		# Finished one-shots stay on their last frame until another action.
		if sprite.sprite_frames.get_animation_loop(clip):
			Binding.play(sprite,clip)
	return true


func on_frame() -> void:
	if active_animation.is_empty() or sprite.frame == last_frame:
		return
	last_frame = sprite.frame
	for sound: Dictionary in Model.outgoing(data, active_animation):
		if sound["kind"] == "sound" and sound["params"]["trigger"] == "frame" and int(sound["params"]["frame"]) == sprite.frame:
			play_sound(str(sound["id"]))


func tick(delta: float) -> void:
	if active_animation.is_empty() or not sprite.is_playing():
		stop_repeats()
		return
	for sound: Dictionary in Model.outgoing(data, active_animation):
		if sound["kind"] != "sound" or sound["params"]["trigger"] != "repeat":
			continue
		var id: String = str(sound["id"])
		elapsed[id] = float(elapsed.get(id, 0.0)) + delta
		if float(elapsed[id]) >= float(sound["params"]["interval"]):
			play_sound(id)
			elapsed[id] = 0.0


func play_sound(id: String) -> void:
	var player: AudioStreamPlayer2D = players.get(id) as AudioStreamPlayer2D
	if player != null and not player.playing:
		player.play()


func stop_repeats() -> void:
	for sound: Dictionary in Model.outgoing(data, active_animation):
		if sound["kind"] == "sound" and sound["params"]["trigger"] == "repeat" and players.has(sound["id"]):
			(players[sound["id"]] as AudioStreamPlayer2D).stop()


func stop() -> void:
	stop_repeats()
	active_animation = ""


func event_scope(scope: String) -> String:
	if scope == "role": return "role:" + str(actor.get_instance_id())
	var game: Node = actor.get_parent()
	while game != null and not "game_blueprint" in game: game = game.get_parent()
	if scope == "game": return "game:" + str(game.get_instance_id()) if game != null else "role:" + str(actor.get_instance_id())
	var key: String = str(data["settings"].get("project_scope",""))
	if key.is_empty() and game != null:
		key = str(game.get("services").get("key")) if game.get("services") != null else str(game.call("settings","session")["save_key"])
	return "project:" + key


func data_input(id: String, port: int, fallback: Variant) -> Variant:
	for edge: Dictionary in data["edges"]:
		if edge["to"] != id or int(edge.get("to_port",0)) != port: continue
		var node: Dictionary = Model.find_node(data,str(edge["from"]))
		if node["kind"] == "boolean": return variables.get(node["params"]["name"],node["params"]["value"])
		if node["kind"] == "typed_value": return Types.initial(node["params"],actor)
		if node["kind"] == "receive_event": return event_values.get(node["id"],fallback)
	return fallback


func dispose() -> void:
	stop()
	if is_instance_valid(bus): bus.call("unsubscribe",actor)
	for player: AudioStreamPlayer2D in players.values():
		if is_instance_valid(player): player.stop()
	players.clear()
	pending.clear()
