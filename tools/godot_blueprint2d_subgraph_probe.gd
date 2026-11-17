extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Library: GDScript = preload("res://addons/ali_assets/game_library.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")


func _initialize() -> void:
	run.call_deferred()


func module(id: String, kind: String, p: Dictionary) -> Dictionary:
	var node: Dictionary = Model.module(id,kind,0,0)
	node["params"].merge(p,true)
	return node


func edge(source: String, port: int, dest: String, input: int = 0) -> Dictionary:
	return {"from":source,"from_port":port,"to":dest,"to_port":input}


func run() -> void:
	var definition: Dictionary = {"type":"parameter_module","version":2,"nodes":[module("argument","module_input",{"name":"amount","value_type":"number","json":"5"}),module("local_value","blackboard",{"name":"local_value","number":0.0}),module("set_local","set_variable",{"name":"local_value"}),module("plus","math",{"b":1.0}),module("wait","wait_task",{"seconds":0.05}),module("result","module_output",{"name":"result","value_type":"number"})],"edges":[edge("argument",0,"set_local",1),edge("set_local",0,"wait"),edge("wait",0,"result"),edge("local_value",0,"plus",0),edge("plus",0,"result",1)],"entry":{"node":"set_local","port":0},"exit":{"node":"result","port":0}}
	var file: FileAccess = FileAccess.open("res://fixtures/parameter.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(definition))
	file.close()
	var graph: Dictionary = Model.scene_preset()
	graph["nodes"].append(module("answer","blackboard",{"name":"answer"}))
	graph["nodes"].append(module("invoke","subgraph",{"path":"res://fixtures/parameter.json","arguments":"{\"amount\":7}"}))
	graph["nodes"].append(module("get_result","collection",{"container":"dictionary","key":"result","value_type":"number"}))
	graph["nodes"].append(module("write_result","set_variable",{"name":"answer"}))
	graph["edges"].append_array([edge("invoke",3,"get_result",0),edge("get_result",0,"write_result",1),edge("invoke",0,"write_result")])
	var compiled: Dictionary = Library.compile(graph)
	assert(not compiled.has("error"),str(compiled.get("error","")))
	assert(Builder.create_scene(graph,"res://subgraph_game.tscn").is_empty())
	assert(DirAccess.rename_absolute("res://fixtures/parameter.json","res://fixtures/parameter_moved.json") == OK)
	var game: Node = (load("res://subgraph_game.tscn") as PackedScene).instantiate()
	root.add_child(game)
	await process_frame
	assert(game.get("initialized"))
	var task: RefCounted = game.get("tasks").call("launch","invoke") as RefCounted
	for frame: int in range(60):
		if task.get("state") != "running": break
		await process_frame
	assert(task.get("state") == "completed",str(task.get("detail")))
	assert(game.get("variables")["answer"] == 8.0)
	assert(not game.get("variables").has("local_value"))
	var stored: Dictionary = game.get("game_blueprint")
	Model.find(stored,"invoke")["params"]["arguments"] = "{\"amount\":\"invalid\"}"
	var invalid: RefCounted = game.get("tasks").call("launch","invoke") as RefCounted
	assert(invalid.get("state") == "failed")
	var recursion: Dictionary = {"type":"parameter_module","version":2,"nodes":[module("recursive","subgraph",{"path":"res://fixtures/recursive.json"})],"edges":[],"entry":{"node":"recursive","port":0},"exit":{"node":"recursive","port":0}}
	file = FileAccess.open("res://fixtures/recursive.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(recursion))
	file.close()
	var bad_graph: Dictionary = Model.scene_preset()
	bad_graph["nodes"].append(module("recursive_call","subgraph",{"path":"res://fixtures/recursive.json"}))
	assert(Library.compile(bad_graph).has("error"))
	game.queue_free()
	await process_frame
	OS.delay_msec(250)
	file = FileAccess.open("res://subgraph-proof.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"typed_named_arguments_and_return":true,"local_variables_isolated":true,"waits_for_async_body":true,"frozen_without_source_json":true,"invalid_input_rejected":true,"recursive_call_rejected":true}))
	file.close()
	quit.call_deferred(0)
