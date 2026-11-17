extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
const Storage: GDScript = preload("res://addons/ali_assets/framework_storage.gd")
const Types: GDScript = preload("res://addons/ali_assets/blueprint_types.gd")
var proof_key: String = ""


func _initialize() -> void:
	run.call_deferred()


func add(graph: Dictionary, id: String, kind: String, p: Dictionary) -> Dictionary:
	var node: Dictionary = Model.module(id,kind,0,0)
	node["params"].merge(p,true)
	graph["nodes"].append(node)
	return node


func wait_done(task: RefCounted) -> void:
	for index: int in range(480):
		if task.get("state") != "running": return
		OS.delay_msec(2)
		await process_frame
	assert(false,"Service task did not settle")


func run() -> void:
	proof_key = "proof_" + str(Time.get_ticks_usec())
	var graph: Dictionary = Model.scene_preset()
	Model.by_kind(graph,"session")["params"]["save_key"] = proof_key
	add(graph,"coins","blackboard",{"name":"coins","number":7.0})
	add(graph,"hp","health",{})
	add(graph,"fsm","fsm",{"name":"motion"})
	var map: Dictionary = add(graph,"map","tilemap",{"operation":"bind","tileset":"res://fixtures/world_tiles.tres","save_key":"floor"})
	for path: String in ["res://service_game.tscn","res://other_game.tscn"]:
		assert(Builder.create_scene(graph,path).is_empty())
		var packed: PackedScene = load(path) as PackedScene
		var root_game: Node = packed.instantiate()
		root_game.set("framework",{"key":proof_key,"menu_scene":"res://other_game.tscn"})
		var actor: Node2D = Node2D.new()
		actor.name = "Player"
		root_game.add_child(actor)
		actor.owner = root_game
		var saved: PackedScene = PackedScene.new()
		assert(saved.pack(root_game) == OK and ResourceSaver.save(saved,path) == OK)
		root_game.free()
		ResourceLoader.load(path,"PackedScene",ResourceLoader.CACHE_MODE_REPLACE)
	var game: Node = (load("res://service_game.tscn") as PackedScene).instantiate()
	root.add_child(game)
	current_scene = game
	await process_frame
	var service: Node = game.get("services") as Node
	var inputs: Node = service.get("inputs") as Node
	var storage: RefCounted = service.get("storage") as RefCounted
	assert(InputMap.action_get_events("MoveLeft").size() >= 2)
	assert(inputs.call("rebind","Jump",[{"key":KEY_L}],"reject") == "")
	assert(not str(inputs.call("rebind","Interact",[{"key":KEY_L}],"reject")).is_empty())
	assert(inputs.call("rebind","Attack",[{"mouse":MOUSE_BUTTON_RIGHT}],"share") == "")
	assert(service.call("save_settings") == "")
	var independent: RefCounted = Storage.new()
	assert(independent.call("configure",proof_key) == "")
	var persisted: Dictionary = independent.call("read_settings")
	assert(persisted["bindings"]["Jump"][0]["key"] == KEY_L)
	inputs.call("reset","Jump")
	assert(inputs.call("serialize_action","Jump")[0]["key"] == KEY_SPACE)
	assert(inputs.call("restore",persisted["bindings"]) == "")
	var settings: Dictionary = {"operation":"volume","channel":"SFX","width":960,"height":540,"window":"windowed"}
	var settings_error: String = service.call("settings_operation",settings,-22.0)
	assert(settings_error.is_empty(),settings_error)
	assert(game.get("mixer_values")["SFX"] == -22.0)
	var actor: Node2D = game.get_node("Player") as Node2D
	actor.position = Vector2(32,48)
	game.get("variables")["coins"] = 23.0
	game.get("program").get("health")["hp"]["value"] = 37.0
	game.get("program").get("machines")["motion"]["current"] = "attack"
	service.get("registered")["quest"] = {"stage":2,"goal":Vector2(8,9)}
	map["params"]["operation"] = "set"
	map["params"]["x"] = 2
	map["params"]["y"] = 3
	var ctx: Dictionary = {"messages":{},"values":{}}
	assert(game.get("world_tools").call("execute",map,0,ctx).get("state") == "completed")
	var saved: RefCounted = service.call("save_slot",1,{"actor":"Player"}) as RefCounted
	assert(saved.get("state") == "completed",str(saved.get("detail")))
	assert(storage.call("read",1)["data"]["variables"]["coins"] == 23.0)
	assert(not storage.call("read",1)["data"].has("settings"))
	actor.position = Vector2(999,999)
	game.get("variables")["coins"] = 99.0
	var loaded: RefCounted = service.call("load_slot",1) as RefCounted
	await wait_done(loaded)
	assert(loaded.get("state") == "completed",str(loaded.get("detail")))
	game = service.call("current_game") as Node
	assert(game != null and game.get("variables")["coins"] == 23.0)
	assert(game.get("program").get("health")["hp"]["value"] == 37.0)
	assert(game.get("program").get("machines")["motion"]["current"] == "attack")
	assert((game.get_node("Player") as Node2D).position.is_equal_approx(Vector2(32,48)))
	assert(service.get("registered")["quest"]["goal"] == Vector2(8,9))
	var layer: TileMapLayer = game.get("world_tools").get("layers")["floor"] as TileMapLayer
	assert(layer.get_cell_source_id(Vector2i(2,3)) == 0)
	assert(game.get("mixer_values")["SFX"] == -22.0)
	assert(service.call("lifecycle","pause").get("state") == "completed")
	assert(paused and game.get("state") == "paused")
	service.call("lifecycle","resume")
	assert(not paused and game.get("state") == "running")
	var sound: Dictionary = Model.module("sound","audio_fx",0,0)
	sound["params"].merge({"path":"res://fixtures/tone.wav","spatial":true},true)
	assert(service.call("execute",game,sound,0,ctx).get("state") == "completed")
	var voice: Node = game.get("audio_tools").get("voices")["sound"] as Node
	assert(voice is AudioStreamPlayer2D and voice.get("playing"))
	game.call("session_command",3)
	await process_frame
	await process_frame
	assert(voice.get("stream_paused"))
	game.call("session_command",3)
	await process_frame
	await process_frame
	assert(not voice.get("stream_paused"))
	var fade: RefCounted = service.call("execute",game,sound,5,ctx) as RefCounted
	await wait_done(fade)
	assert(fade.get("state") == "completed" and not voice.get("playing"))
	var corrupted: String = storage.call("slot_path",2)
	var bad: FileAccess = FileAccess.open(corrupted,FileAccess.WRITE)
	bad.store_string("broken json")
	bad.close()
	assert(storage.call("read",2).has("error") and FileAccess.file_exists(corrupted))
	assert(storage.call("remove",2) == "" and storage.call("remove",1) == "")
	assert(not storage.call("save",3,{"unsupported":Thread.new()}).is_empty())
	var next: RefCounted = service.get("scenes").call("request","res://other_game.tscn",0.05) as RefCounted
	await wait_done(next)
	assert(next.get("state") == "completed")
	assert(current_scene.scene_file_path == "res://other_game.tscn")
	current_scene.queue_free()
	current_scene = null
	await process_frame
	OS.delay_msec(250)
	var file: FileAccess = FileAccess.open("res://services-proof.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"inputmap_multikey_mouse_conflict_reset_persist":true,"settings_independent_of_save":true,"scoped_audio_settings_restored":true,"save_scene_then_actor_variables_maps_registered":true,"game_manager_pause_resume":true,"positional_audio_and_fade":true,"corrupt_slot_preserved_and_delete":true,"unsafe_object_save_rejected":true,"threaded_scene_switch_fade":true}))
	file.close()
	quit.call_deferred(0)
