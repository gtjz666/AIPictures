extends Node2D
## A self-contained game assembled from editable modules, with no autoloads.
const API_VERSION: int = 6
const Animations: GDScript = preload("game_animations.gd")
const Tasks: GDScript = preload("game_tasks.gd")
const Features: GDScript = preload("game_features.gd")
const WorldTools: GDScript = preload("game_world_tools.gd")
const Services: GDScript = preload("framework_services.gd")
const AudioTools: GDScript = preload("game_audio_tools.gd")
const Link: GDScript = preload("resource_link.gd")
const Widgets: GDScript = preload("game_widgets.gd")
const Library: GDScript = preload("game_library.gd")
const Program: GDScript = preload("game_program.gd")
const Model: GDScript = preload("game_model.gd")
const Assets: GDScript = preload("game_assets.gd")
const Actor: GDScript = preload("game_actor.gd")
const World: GDScript = preload("game_world.gd")
const Spawner: GDScript = preload("game_spawner.gd")
const Audio: GDScript = preload("game_audio.gd")
const Hud: GDScript = preload("game_hud.gd")
@export var game_blueprint: Dictionary = {}
@export var compiled_blueprint: Dictionary = {}
@export var compiled_signature: String = ""
@export var framework: Dictionary = {}
var program: RefCounted
var debug_path: String = ""
var state: String = "waiting"
var score: int = 0
var best: int = 0
var elapsed: float = 0.0
var base_size: Vector2i = Vector2i(960, 540)
var ground_y: float = 432.0
var current_speed: float = 300.0
var actor: CharacterBody2D
var world: Node2D
var spawner: Node2D
var hud: CanvasLayer
var audio: Dictionary = {}
var bus_names: Dictionary = {}
var mixer_values: Dictionary = {}
var variables: Dictionary = {}
var modules: Dictionary = {}
var timers: Dictionary = {}
var delayed: Array[Dictionary] = []
var queue: Array[Dictionary] = []
var routing: bool = false
var generation: int = 0
var profile: ConfigFile = ConfigFile.new()
var profile_path: String
var save_countdown: float = -1.0
var previous_scale: Vector2i
var previous_mode: Window.ContentScaleMode = Window.CONTENT_SCALE_MODE_DISABLED
var previous_aspect: Window.ContentScaleAspect = Window.CONTENT_SCALE_ASPECT_KEEP
var initialized: bool = false
var animations: Node
var tasks: Node
var features: Node
var services: Node
var world_tools: Node
var audio_tools: Node
var capturing: bool = false
var captured: Array[Dictionary] = []
var captured_events: Array[Dictionary] = []
var widgets: Node
var debug_clock: float = 0.0
var debug_source_signature: String = ""


func settings(kind: String) -> Dictionary:
	return Model.by_kind(game_blueprint, kind)["params"]


func _ready() -> void:
	if Engine.is_editor_hint():
		return
	initialize_game.call_deferred()


func initialize_game() -> void:
	if not is_inside_tree(): return
	debug_source_signature = Library.signature(game_blueprint)
	var prepared: Dictionary = {"data": compiled_blueprint} if not compiled_blueprint.is_empty() and compiled_signature == Library.signature(game_blueprint) else Library.compile(game_blueprint)
	var problem: String = str(prepared.get("error", ""))
	if problem.is_empty():
		game_blueprint = Link.normalize(Model.upgrade(prepared["data"]))
		problem = Model.validate(game_blueprint, true)
	if not problem.is_empty():
		push_error("游戏蓝图：" + problem)
		set_process(false)
		return
	var screen: Dictionary = settings("screen")
	base_size = Vector2i(int(screen["width"]), int(screen["height"]))
	var window: Window = get_window()
	previous_scale = window.content_scale_size
	previous_mode = window.content_scale_mode
	previous_aspect = window.content_scale_aspect
	window.content_scale_size = base_size
	window.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
	window.content_scale_aspect = Window.CONTENT_SCALE_ASPECT_KEEP if screen["aspect"] == "keep" else Window.CONTENT_SCALE_ASPECT_EXPAND
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST if screen["pixel"] else CanvasItem.TEXTURE_FILTER_LINEAR
	profile_path = "user://ali_game_" + str(settings("session")["save_key"]) + ".cfg"
	if FileAccess.file_exists(profile_path):
		profile.load(profile_path)
	best = maxi(0, int(profile.get_value("score", "best", 0)))
	setup_buses()
	services = Services.obtain(get_tree(),framework,str(settings("session")["save_key"]),Services)
	if not Model.by_kind(game_blueprint, "runner").is_empty() and not Model.by_kind(game_blueprint, "world").is_empty():
		world = World.new()
		world.name = "World"
		add_child(world)
		world.call("setup", self, settings("world"), base_size.x, base_size.y)
		ground_y = float(world.get("ground_y"))
		var frames: SpriteFrames = Assets.frames() if str(settings("runner")["frames"]).is_empty() else Model.frames_at(str(settings("runner")["frames"]))
		actor = Actor.new()
		actor.name = "Runner"
		actor.call("setup", self, settings("runner"), frames, Vector2(base_size.x * 0.17, ground_y))
		add_child(actor)
		spawner = Spawner.new()
		spawner.name = "ObstacleSpawner"
		add_child(spawner)
		spawner.call("setup", self, settings("spawner"), actor)
	for node: Dictionary in game_blueprint["nodes"]:
		var kind: String = str(node["kind"])
		var id: String = str(node["id"])
		var p: Dictionary = node["params"]
		if kind == "audio":
			var sound: Node = Audio.new()
			sound.name = "Audio_" + id
			add_child(sound)
			sound.call("setup", self, id, p, bus_names[p["channel"]])
			audio[id] = sound
		elif kind == "boolean":
			variables[p["name"]] = p["value"]
		elif kind == "custom" and not str(p["script"]).is_empty():
			modules[id] = (load(str(p["script"])) as GDScript).new()
		elif kind == "timer":
			timers[id] = {"active": false, "elapsed": 0.0}
	hud = Hud.new()
	hud.name = "GameUI"
	add_child(hud)
	hud.call("setup", self, settings("hud"))
	if framework.get("native_menus",false): hud.hide()
	program = Program.new()
	program.call("setup", self)
	animations = Animations.new()
	animations.name = "BlueprintAnimations"
	add_child(animations)
	animations.call("setup", self)
	tasks = Tasks.new()
	tasks.name = "BlueprintTasks"
	add_child(tasks)
	tasks.call("setup", self)
	features = Features.new()
	features.name = "BlueprintFeatures"
	add_child(features)
	features.call("setup", self)
	world_tools = WorldTools.new()
	world_tools.name = "WorldTools"
	add_child(world_tools)
	world_tools.call("setup", self)
	audio_tools = AudioTools.new()
	audio_tools.name = "AudioTools"
	add_child(audio_tools)
	audio_tools.call("setup",self)
	widgets = Widgets.new()
	widgets.name = "BlueprintWidgets"
	add_child(widgets)
	widgets.call("setup", self)
	debug_path = "user://ali_blueprint_" + str(settings("session")["save_key"]) + ".json"
	hud.call("refresh_health")
	initialized = true
	services.call("attach_game",self)
	queue_redraw()
	set_process_unhandled_key_input(true)


func setup_buses() -> void:
	var prefix: String = "AlI_" + str(get_instance_id()) + "_"
	for channel: String in ["Master", "BGM", "SFX", "UI"]:
		var index: int = AudioServer.bus_count
		AudioServer.add_bus()
		var bus: String = prefix + channel
		AudioServer.set_bus_name(index, bus)
		AudioServer.set_bus_send(index, &"Master" if channel == "Master" else StringName(bus_names["Master"]))
		bus_names[channel] = bus
		set_volume(channel, clampf(float(profile.get_value("audio", channel, settings("mixer")[channel])), -60, 6), false)


func set_volume(channel: String, value: float, persist: bool = true) -> void:
	if not bus_names.has(channel):
		return
	value = clampf(value, -60, 6)
	mixer_values[channel] = value
	var index: int = AudioServer.get_bus_index(str(bus_names[channel]))
	AudioServer.set_bus_volume_db(index, value)
	AudioServer.set_bus_mute(index, value <= -60)
	if persist:
		profile.set_value("audio", channel, value)
		save_countdown = 0.5
		if is_instance_valid(services):
			if not services.get("settings").has("volumes"): services.get("settings")["volumes"] = {}
			services.get("settings")["volumes"][channel] = value
			services.call("save_settings")


func _unhandled_key_input(event_input: InputEvent) -> void:
	if not initialized or not event_input is InputEventKey or event_input.echo:
		return
	if services != null and services.get("inputs").call("deliver",self,event_input):
		get_viewport().set_input_as_handled()
		return
	if not framework.is_empty():
		if event_input.is_pressed() and event_input.is_action("Jump"): event("input",1 if state == "waiting" else 2 if state == "dead" else 0); get_viewport().set_input_as_handled()
		return
	var key: int = event_input.physical_keycode if event_input.physical_keycode != 0 else event_input.keycode
	var handled: bool = false
	for node: Dictionary in game_blueprint["nodes"]:
		if node["kind"] == "key_event" and int(node["params"]["key"]) == key and (not node["params"]["running_only"] or state == "running"):
			emit_port(str(node["id"]), 0 if event_input.pressed else 1)
			handled = true
	if not event_input.pressed:
		if handled:
			get_viewport().set_input_as_handled()
		return
	var input: Dictionary = settings("input")
	if key == int(input["pause"]):
		event("input", 3)
	elif key == int(input["restart"]):
		event("input", 2)
	elif key == int(input["jump"]):
		event("input", 1 if state == "waiting" else 2 if state == "dead" else 0)
	else:
		if not handled:
			return
	get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	if not initialized:
		return
	if OS.is_debug_build():
		debug_clock += delta
		if debug_clock >= 0.5: debug_clock = 0.0; write_debug()
	if services != null: services.get("inputs").call("tick",self)
	if save_countdown >= 0:
		save_countdown -= delta
		if save_countdown < 0:
			profile.save(profile_path)
	if state == "paused":
		return
	program.call("tick", delta)
	var due: Array[Dictionary] = delayed
	delayed = []
	for entry: Dictionary in due:
		if int(entry.get("generation", generation)) != generation:
			continue
		entry["remaining"] = float(entry["remaining"]) - delta
		if float(entry["remaining"]) <= 0:
			emit_port(str(entry["id"]), 0)
		else:
			delayed.append(entry)
	if state != "running":
		return
	elapsed += delta
	var previous_score: int = score
	score += int(floor(elapsed * float(settings("session")["points_per_second"]))) - int(floor((elapsed - delta) * float(settings("session")["points_per_second"])))
	if score != previous_score:
		event("session", 5)
	if is_instance_valid(spawner):
		current_speed = minf(float(settings("spawner")["max_speed"]), float(settings("spawner")["speed"]) + elapsed * float(settings("spawner")["acceleration"]))
	if is_instance_valid(world):
		world.call("tick", delta, current_speed)
	if is_instance_valid(spawner):
		spawner.call("tick", delta, current_speed)
	for id: String in timers:
		var timer: Dictionary = timers[id]
		if timer["active"]:
			timer["elapsed"] = float(timer["elapsed"]) + delta
			var p: Dictionary = Model.find(game_blueprint, id)["params"]
			if float(timer["elapsed"]) >= float(p["seconds"]):
				timer["elapsed"] = fmod(float(timer["elapsed"]), float(p["seconds"]))
				timer["active"] = bool(p["repeat"])
				emit_port(id, 0)


func event(kind: String, port: int) -> void:
	var node: Dictionary = Model.by_kind(game_blueprint, kind)
	if not node.is_empty():
		emit_port(str(node["id"]), port)


func emit_port(source: String, port: int) -> void:
	if capturing:
		captured.append({"id":source,"port":port})
		return
	for edge: Dictionary in game_blueprint["edges"]:
		if edge["from"] != source or int(edge.get("from_port", 0)) != port:
			continue
		if Model.port_type(game_blueprint, source, port, true) != 0:
			continue
		queue.append({"id": edge["to"], "port": int(edge.get("to_port", 0)), "messages": program.get("messages").duplicate() if program != null else {}})
	drain()


func queue_event(id: String, payload: Variant) -> void:
	if capturing:
		captured_events.append({"id":id,"payload":payload})
		return
	queue.append({"event": true, "id": id, "payload": payload})
	drain()


func drain() -> void:
	if routing:
		return
	routing = true
	var budget: int = 512
	while not queue.is_empty() and budget > 0:
		var request: Dictionary = queue.pop_front()
		if request.get("event", false):
			program.get("messages")[request["id"]] = request["payload"]
			emit_port(str(request["id"]), 0)
		else:
			program.set("messages", request.get("messages", {}))
			deliver(str(request["id"]), int(request["port"]))
		budget -= 1
	if not queue.is_empty():
		queue.clear()
		program.call("fault", "", "游戏蓝图执行超过512次预算，已停止本次事件链。")
		write_debug()
	routing = false


func deliver(id: String, port: int) -> void:
	var node: Dictionary = Model.find(game_blueprint, id)
	if node.is_empty():
		return
	if features != null and features.call("has_kind", str(node["kind"])) or node["kind"] == "task_group":
		tasks.call("launch", id, port)
		return
	program.get("cache").clear()
	program.call("record", id, "执行输入 " + str(port))
	var p: Dictionary = node["params"]
	match str(node["kind"]):
		"button": widgets.call("command", id, port)
		"session": session_command(port)
		"runner": actor.call("command", port)
		"world": world.call("command", port)
		"spawner": spawner.call("command", port)
		"hud": hud.call("command", port)
		"audio": (audio[id] as Node).call("command", port)
		"timer":
			if port != 2:
				timers[id]["active"] = port == 0
			if port in [0, 2]:
				timers[id]["elapsed"] = 0.0
		"delay":
			if delayed.size() < 128:
				delayed.append({"id": id, "remaining": float(p["seconds"]), "generation": generation})
			else:
				program.call("fault", id, "延迟待办已达到128项，本次等待未加入。")
		"sequence":
			emit_port(id, 0)
			emit_port(id, 1)
		"branch":
			var condition: bool = state == "running" if p["condition"] == "running" else (is_instance_valid(actor) and actor.is_on_floor()) if p["condition"] == "grounded" else state == "dead" if p["condition"] == "dead" else state == "paused" if p["condition"] == "paused" else score >= float(p["threshold"])
			for edge: Dictionary in game_blueprint["edges"]:
				if edge["to"] == id and int(edge.get("to_port", 0)) == 1:
					condition = bool(program.call("input_value", id, 1, false))
			emit_port(id, 0 if condition else 1)
		"custom":
			if modules.has(id) and (modules[id] as RefCounted).has_method("execute"):
				var result: Variant = (modules[id] as RefCounted).call("execute", {"game": self, "actor": actor, "variables": variables, "score": score, "delta": get_process_delta_time()})
				if result is Dictionary:
					emit_port(id, clampi(int(result.get("output", 0)), 0, 1))
		_: program.call("execute", node, port)


func session_command(port: int) -> void:
	match port:
		0:
			if state not in ["waiting", "dead"]:
				return
			state = "running"
			score = 0
			elapsed = 0
			if tasks != null: tasks.call("cancel_all")
			if animations != null: animations.call("cancel_all")
			generation += 1
			queue.clear()
			delayed.clear()
			for timer: Dictionary in timers.values():
				timer["active"] = false
				timer["elapsed"] = 0.0
			program.call("pause", false)
			program.call("reset")
			hud.call("refresh_health")
			event("session", 0)
			event("session", 5)
		1:
			if state not in ["running", "paused"]:
				return
			state = "dead"
			best = maxi(best, score)
			profile.set_value("score", "best", best)
			profile.save(profile_path)
			program.call("pause", true)
			event("session", 1)
			if framework.get("native_menus",false): services.set("state","ended"); services.call("notify","ended")
		2:
			state = "waiting"
			for sound: Node in audio.values():
				sound.call("command", 1)
			if is_instance_valid(actor):
				actor.get("sprite").set("speed_scale", 1.0)
			event("session", 2)
			session_command(0)
			if framework.get("native_menus",false): services.call("notify","restarted")
		3:
			if state not in ["running", "paused"]:
				return
			state = "paused" if state == "running" else "running"
			program.call("pause", state == "paused")
			if is_instance_valid(actor):
				actor.get("sprite").set("speed_scale", 0.0 if state == "paused" else 1.0)
			for sound: Node in audio.values():
				if sound.get("params")["channel"] != "UI":
					sound.call("pause", state == "paused")
			event("session", 3 if state == "paused" else 4)
		4:
			add_points(int(settings("session")["obstacle_points"]))


func add_points(amount: int) -> void:
	if state == "running":
		score = maxi(0, score + amount)
		event("session", 5)


func write_debug() -> void:
	if OS.is_debug_build() and program != null and not debug_path.is_empty():
		var file: FileAccess = FileAccess.open(debug_path, FileAccess.WRITE)
		if file != null:
			var snapshot: Dictionary = program.call("report")
			snapshot["signature"] = debug_source_signature
			snapshot["nodes"] = tasks.get("last_states").duplicate(true) if tasks != null else {}
			for event_row: Dictionary in snapshot["events"]:
				var id: String = str(event_row.get("source",""))
				if not snapshot["nodes"].has(id): snapshot["nodes"][id] = {"state":"failed" if "错误" in str(event_row["detail"]) else "completed","detail":event_row["detail"]}
			file.store_string(JSON.stringify(Program.Types.encode(snapshot,self), "\t"))
			file.close()


func _exit_tree() -> void:
	if not initialized:
		return
	if services != null: services.call("detach_game",self)
	if tasks != null: tasks.call("cancel_all")
	if animations != null: animations.call("cancel_all")
	write_debug()
	program.call("dispose")
	for sound: Node in audio.values():
		if is_instance_valid(sound):
			sound.call("command", 1)
	if save_countdown >= 0:
		profile.save(profile_path)
	var channels: Array = bus_names.keys()
	channels.reverse()
	for channel: String in channels:
		var index: int = AudioServer.get_bus_index(str(bus_names[channel]))
		if index > 0:
			AudioServer.remove_bus(index)
	var window: Window = get_window()
	if window != null and window.content_scale_size == base_size:
		window.content_scale_size = previous_scale
		window.content_scale_mode = previous_mode
		window.content_scale_aspect = previous_aspect


func _draw() -> void:
	if initialized and not is_instance_valid(world):
		draw_rect(Rect2(Vector2.ZERO, Vector2(base_size)), Color("dceef0"))


func capture_node(id: String, port: int, context: Dictionary) -> Array[Dictionary]:
	var previous: Dictionary = program.get("messages")
	program.set("messages", context.get("messages", {}))
	features.set("context", context)
	capturing = true
	captured = []
	captured_events = []
	deliver(id, port)
	capturing = false
	var emissions: Array[Dictionary] = captured
	var events: Array[Dictionary] = captured_events
	captured = []
	captured_events = []
	context["messages"] = program.get("messages").duplicate(true)
	program.set("messages", previous)
	for entry: Dictionary in events: queue_event.call_deferred(str(entry["id"]), entry["payload"])
	return emissions


func _unhandled_input(input_event: InputEvent) -> void:
	if not initialized or input_event is InputEventKey or services == null: return
	if services.get("inputs").call("deliver",self,input_event): get_viewport().set_input_as_handled()
