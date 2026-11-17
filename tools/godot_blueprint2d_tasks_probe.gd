extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
const Types: GDScript = preload("res://addons/ali_assets/blueprint_types.gd")
var game: Node2D
var target: Node2D


func _initialize() -> void:
	run.call_deferred()


func add(graph: Dictionary, id: String, kind: String, p: Dictionary = {}) -> void:
	var node: Dictionary = Model.module(id, kind, 0, 0)
	node["params"].merge(p, true)
	graph["nodes"].append(node)


func wire(graph: Dictionary, source: String, port: int, dest: String, input: int = 0) -> void:
	graph["edges"].append({"from":source,"from_port":port,"to":dest,"to_port":input})


func wait_done(task: RefCounted, max_frames: int = 180) -> void:
	for frame: int in range(max_frames):
		if task.get("state") != "running": return
		await process_frame
	assert(false, "Task did not settle")


func run() -> void:
	var graph: Dictionary = Model.scene_preset()
	add(graph, "serial", "task_group", {"mode":"serial"})
	add(graph, "parallel", "task_group", {"mode":"parallel","branches":3})
	add(graph,"nested","task_group",{"mode":"serial"})
	add(graph,"nested_parallel","task_group",{"mode":"parallel"})
	add(graph,"wait_a","wait_task",{"seconds":0.1})
	add(graph,"wait_b","wait_task",{"seconds":0.2})
	add(graph,"after_nested","log")
	wire(graph,"nested",0,"nested_parallel")
	wire(graph,"nested",1,"after_nested")
	wire(graph,"nested_parallel",0,"wait_a")
	wire(graph,"nested_parallel",1,"wait_b")
	add(graph, "move_a", "animation", {"target":"Target","mode":"position","x":30.0,"y":0.0,"seconds":0.1})
	add(graph, "move_b", "animation", {"target":"Target","mode":"position","x":-20.0,"y":0.0,"seconds":0.1})
	add(graph, "scale", "animation", {"target":"Target","factor":1.5,"seconds":0.2})
	add(graph, "color", "animation", {"target":"Target","mode":"color","color":"ff000080","seconds":0.15})
	for id: String in ["after_a","after_b","after_serial","after_parallel"]: add(graph, id, "log")
	wire(graph,"serial",0,"move_a")
	wire(graph,"serial",1,"move_b")
	wire(graph,"move_a",0,"after_a")
	wire(graph,"move_b",0,"after_b")
	wire(graph,"serial",4,"after_serial")
	wire(graph,"parallel",0,"move_a")
	wire(graph,"parallel",1,"scale")
	wire(graph,"parallel",2,"color")
	wire(graph,"parallel",4,"after_parallel")
	assert(Model.validate(graph, true).is_empty(), Model.validate(graph, true))
	assert(Builder.create_scene(graph, "res://task_game.tscn").is_empty())
	game = (load("res://task_game.tscn") as PackedScene).instantiate() as Node2D
	target = Node2D.new()
	target.name = "Target"
	game.add_child(target)
	root.add_child(game)
	await process_frame
	assert(game.get("initialized"))
	var tasks: Node = game.get("tasks") as Node
	var animations: Node = game.get("animations") as Node
	var serial: RefCounted = tasks.call("launch", "serial") as RefCounted
	await wait_done(serial)
	assert(serial.get("state") == "completed", str(serial.get("detail")))
	assert(is_equal_approx(target.position.x, 10.0))
	var trace: Array = game.get("program").get("trace")
	var a: Array = trace.filter(func(row: Dictionary) -> bool: return row["node"] == "after_a")
	var b: Array = trace.filter(func(row: Dictionary) -> bool: return row["node"] == "after_b")
	assert(float(b[0]["time"]) - float(a[0]["time"]) >= 0.08)
	var start_time: float = game.get("program").get("clock")
	var parallel: RefCounted = tasks.call("launch", "parallel") as RefCounted
	await wait_done(parallel)
	assert(parallel.get("state") == "completed", str(parallel.get("detail")))
	assert(float(game.get("program").get("clock")) - start_time < 0.3)
	assert(target.scale.is_equal_approx(Vector2(1.5,1.5)) and is_equal_approx(target.modulate.a, 128.0/255.0))
	var original: Vector2 = target.position
	var restored: RefCounted = animations.call("start", {"mode":"position","target":"Target","x":40.0,"seconds":0.05,"relative":true,"restore":true}) as RefCounted
	await wait_done(restored)
	assert(target.position.is_equal_approx(original))
	var paused: RefCounted = animations.call("start", {"mode":"position","target":"Target","x":40.0,"seconds":0.2,"relative":true}) as RefCounted
	game.set("state", "paused")
	await process_frame
	var frozen: Vector2 = target.position
	for frame: int in range(12): await process_frame
	assert(target.position.is_equal_approx(frozen) and paused.get("state") == "running")
	var ui: RefCounted = animations.call("start", {"mode":"scale","target":"Target","factor":2.0,"seconds":0.05,"ui":true}) as RefCounted
	await wait_done(ui)
	assert(ui.get("state") == "completed")
	game.set("state", "running")
	await wait_done(paused)
	var loop: RefCounted = animations.call("start", {"mode":"scale","target":"Target","loops":0,"wait":true}) as RefCounted
	assert(loop.get("state") == "failed")
	var cancelled: RefCounted = tasks.call("launch", "serial") as RefCounted
	cancelled.call("cancel")
	assert(cancelled.get("state") == "cancelled")
	var native: Animation = Animation.new()
	native.length = 0.1
	var track: int = native.add_track(Animation.TYPE_VALUE)
	native.track_set_path(track, NodePath(".:position"))
	native.track_insert_key(track,0,Vector2.ZERO)
	native.track_insert_key(track,0.1,Vector2(80,40))
	assert(ResourceSaver.save(native,"res://fixtures/position.tres") == OK)
	var before: String = FileAccess.get_sha256("res://fixtures/position.tres")
	original = target.position
	var playback: RefCounted = animations.call("start", {"mode":"animation","target":"Target","animation":"res://fixtures/position.tres","loops":1,"restore":true}) as RefCounted
	await wait_done(playback)
	assert(playback.get("state") == "completed",str(playback.get("detail")))
	assert(target.position.is_equal_approx(original))
	assert(FileAccess.get_sha256("res://fixtures/position.tres") == before)
	var nested_start: float = float(game.get("program").get("clock"))
	var nested: RefCounted = tasks.call("launch","nested") as RefCounted
	await wait_done(nested)
	assert(nested.get("state") == "completed")
	var nested_trace: Array = game.get("program").get("trace").filter(func(row: Dictionary) -> bool: return row["node"] == "after_nested")
	assert(float(nested_trace[-1]["time"])-nested_start >= 0.19)
	var player: AnimationPlayer = AnimationPlayer.new()
	player.name = "Player"
	target.add_child(player)
	var library: AnimationLibrary = AnimationLibrary.new()
	library.add_animation("existing",native)
	player.add_animation_library("",library)
	playback = animations.call("start",{"mode":"animation","target":"Target/Player","clip":"existing","loops":2,"speed":2.0,"reverse":true,"restore":true}) as RefCounted
	await wait_done(playback)
	assert(playback.get("state") == "completed" and player.get_animation_library_list().size() == 1)
	var bad_animation: Animation = native.duplicate(true) as Animation
	bad_animation.track_set_path(0,NodePath("Missing:position"))
	assert(ResourceSaver.save(bad_animation,"res://fixtures/remap.tres") == OK)
	var bad: RefCounted = animations.call("start",{"mode":"animation","target":"Target","animation":"res://fixtures/remap.tres"}) as RefCounted
	assert(bad.get("state") == "failed")
	playback = animations.call("start",{"mode":"animation","target":"Target","animation":"res://fixtures/remap.tres","remap":"{\"Missing\":\".\"}","restore":true}) as RefCounted
	await wait_done(playback)
	assert(playback.get("state") == "completed")
	var deleted: RefCounted = animations.call("start", {"mode":"scale","target":"Target","seconds":3.0}) as RefCounted
	target.free()
	await wait_done(deleted)
	assert(deleted.get("state") == "failed")
	var encoded: Variant = Types.encode({"p":Vector2(1,2),"c":Color.RED,"array":[3,true]})
	assert(Types.decode(JSON.parse_string(JSON.stringify(encoded)))["p"] == Vector2(1,2))
	game.queue_free()
	await process_frame
	OS.delay_msec(250)
	var file: FileAccess = FileAccess.open("res://tasks-proof.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"serial_actual_completion":true,"parallel_all_branches":true,"transform_and_rgba":true,"restore":true,"game_pause_and_ui_continue":true,"infinite_wait_rejected":true,"explicit_cancel":true,"native_animation_copy_and_restore":true,"deleted_target_fails":true,"typed_codec":true}))
	file.close()
	quit.call_deferred(0)
