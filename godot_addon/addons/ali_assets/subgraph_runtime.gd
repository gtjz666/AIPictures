extends Node2D
## A call-local interpreter sharing native services, never a second full game.
const Program: GDScript = preload("game_program.gd")
const Features: GDScript = preload("game_features.gd")
const Tasks: GDScript = preload("game_tasks.gd")
const Audio: GDScript = preload("game_audio.gd")
const Task: GDScript = preload("blueprint_task.gd")
var binding_root: Node
var host: Node
var game_blueprint: Dictionary
var program: RefCounted
var features: Node
var tasks: Node
var animations: Node
var services: Node
var world_tools: Node
var audio_tools: Node
var widgets: Node
var hud: CanvasLayer
var actor: CharacterBody2D
var audio: Dictionary = {}
var bus_names: Dictionary = {}
var variables: Dictionary = {}
var modules: Dictionary = {}
var initialized: bool = true
var state: String:
	get: return str(host.get("state")) if is_instance_valid(host) else "ended"
var score: int:
	get: return int(host.get("score")) if is_instance_valid(host) else 0
var elapsed: float:
	get: return float(host.get("elapsed")) if is_instance_valid(host) else 0.0
var best: int:
	get: return int(host.get("best")) if is_instance_valid(host) else 0
var current_speed: float:
	get: return float(host.get("current_speed")) if is_instance_valid(host) else 0.0
var captured: Array[Dictionary] = []
var captured_events: Array[Dictionary] = []


func setup(controller: Node, definition: Dictionary, context: Dictionary, origin: String) -> RefCounted:
	host = controller
	binding_root = controller.get("binding_root") if "binding_root" in controller and controller.get("binding_root") != null else controller
	game_blueprint = {"nodes":definition["nodes"].duplicate(true),"edges":definition["edges"].duplicate(true)}
	for node: Dictionary in game_blueprint["nodes"]: node["_origin"] = origin
	animations = host.get("animations")
	services = host.get("services")
	world_tools = host.get("world_tools")
	audio_tools = host.get("audio_tools")
	widgets = host.get("widgets")
	hud = host.get("hud") as CanvasLayer
	actor = host.get("actor") as CharacterBody2D
	bus_names = host.get("bus_names")
	program = Program.new()
	program.call("setup",self)
	for node: Dictionary in game_blueprint["nodes"]:
		if node["kind"] == "custom": modules[node["id"]] = (load(str(node["params"]["script"])) as GDScript).new()
		elif node["kind"] == "audio":
			var voice: Node = Audio.new()
			add_child(voice)
			voice.call("setup",self,str(node["id"]),node["params"],bus_names[node["params"]["channel"]])
			audio[node["id"]] = voice
	features = Features.new()
	add_child(features)
	features.call("setup",self)
	tasks = Tasks.new()
	add_child(tasks)
	tasks.call("setup",self)
	context["exit"] = definition["exit"]
	context["exit_seen"] = {"value":false}
	context["returns"] = {}
	features.set("context",context)
	return tasks.call("launch",str(definition["entry"]["node"]),int(definition["entry"]["port"]),context) as RefCounted


func settings(kind: String) -> Dictionary:
	return host.call("settings",kind)


func emit_port(id: String, port: int) -> void:
	captured.append({"id":id,"port":port})


func queue_event(id: String, payload: Variant) -> void:
	captured_events.append({"id":id,"payload":payload})


func deliver(id: String, port: int) -> void:
	var node: Dictionary = {}
	for candidate: Dictionary in game_blueprint["nodes"]:
		if candidate["id"] == id: node = candidate
	if node.is_empty(): return
	program.get("cache").clear()
	program.call("record",id,"子图执行 " + str(port))
	if node["kind"] == "audio": audio[id].call("command",port)
	elif node["kind"] == "sequence": emit_port(id,0); emit_port(id,1)
	elif node["kind"] == "branch":
		var condition: bool = bool(program.call("input_value",id,1,state == "running"))
		emit_port(id,0 if condition else 1)
	elif node["kind"] == "custom":
		var result: Variant = modules[id].call("execute",{"game":self,"actor":actor,"variables":variables,"score":score,"delta":get_process_delta_time()})
		if result is Dictionary: emit_port(id,clampi(int(result.get("output",0)),0,1))
	else: program.call("execute",node,port)


func capture_node(id: String, port: int, context: Dictionary) -> Array[Dictionary]:
	program.set("messages",context.get("messages",{}))
	features.set("context",context)
	captured = []
	captured_events = []
	deliver(id,port)
	var emissions: Array[Dictionary] = captured
	captured = []
	for event: Dictionary in captured_events: host.call("queue_event",str(event["id"]),event["payload"])
	captured_events = []
	return emissions


func _process(delta: float) -> void:
	if program != null and state != "paused": program.call("tick",delta)


func _exit_tree() -> void:
	if tasks != null: tasks.call("cancel_all")
	if program != null:
		if is_instance_valid(host):
			for row: Dictionary in program.get("trace"): host.get("program").get("trace").append(row)
			while host.get("program").get("trace").size() > 256: host.get("program").get("trace").pop_front()
			for id: String in program.get("instances"): host.get("program").get("instances")[str(get_instance_id())+"_"+id] = program.get("instances")[id]
		program.call("dispose")
