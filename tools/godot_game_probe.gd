extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
const Assets: GDScript = preload("res://addons/ali_assets/game_assets.gd")


func _initialize() -> void:
	run.call_deferred()


func physics(count: int) -> void:
	for index: int in range(count):
		await physics_frame


func run() -> void:
	var data: Dictionary = Model.preset()
	Model.by_kind(data, "session")["params"]["save_key"] = "probe_" + str(Time.get_ticks_usec())
	assert(Model.validate(data, true).is_empty(), Model.validate(data, true))
	assert(Builder.create_scene(data, "res://runner_game.tscn").is_empty())
	assert(not Builder.create_scene(data, "res://runner_game.tscn").is_empty())
	var buses: int = AudioServer.bus_count
	var packed: PackedScene = load("res://runner_game.tscn") as PackedScene
	var game: Node2D = packed.instantiate() as Node2D
	root.add_child(game)
	await process_frame
	assert(bool(game.get("initialized")))
	assert(game.get("state") == "waiting" and AudioServer.bus_count == buses + 4)
	assert(root.content_scale_size == Vector2i(960, 540))
	var actor: CharacterBody2D = game.get("actor") as CharacterBody2D
	var sprite: AnimatedSprite2D = actor.get("sprite") as AnimatedSprite2D
	var hud: CanvasLayer = game.get("hud") as CanvasLayer
	(hud.get("primary") as Button).pressed.emit()
	await physics(8)
	assert(game.get("state") == "running" and actor.is_on_floor())
	assert(sprite.animation == &"walk_right")
	var music: Node = game.get("audio")["music"]
	var steps: Node = game.get("audio")["steps"]
	assert(music.get("players")[0].playing and int(steps.get("triggers")) > 0)
	assert(not AudioServer.is_bus_mute(AudioServer.get_bus_index(str(game.get("bus_names")["BGM"]))))
	var music_player: AudioStreamPlayer = music.get("players")[0] as AudioStreamPlayer
	music_player.seek(music_player.stream.get_length() - 0.01)
	OS.delay_msec(100)
	await process_frame
	await process_frame
	assert(music_player.playing and music_player.get_playback_position() < 1.0)
	game.call("event", "input", 0)
	await physics(4)
	assert(actor.velocity.y < 0 and not actor.is_on_floor() and sprite.animation == &"jump_right")
	var jump_count: int = int(game.get("audio")["jump_sfx"].get("triggers"))
	game.call("event", "input", 0)
	await physics(2)
	assert(int(game.get("audio")["jump_sfx"].get("triggers")) == jump_count)
	await physics(55)
	assert(actor.is_on_floor())
	game.call("event", "input", 3)
	var saved_score: int = int(game.get("score"))
	var saved_offset: float = float(game.get("world").get("offset"))
	var saved_y: float = actor.position.y
	await physics(20)
	assert(game.get("state") == "paused" and int(game.get("score")) == saved_score and actor.position.y == saved_y)
	assert(float(game.get("world").get("offset")) == saved_offset and music.get("players")[0].stream_paused)
	game.call("set_volume", "BGM", -60.0)
	assert(AudioServer.is_bus_mute(AudioServer.get_bus_index(str(game.get("bus_names")["BGM"]))))
	game.call("event", "input", 3)
	assert(game.get("state") == "running" and not music.get("players")[0].stream_paused)
	var spawner: Node2D = game.get("spawner") as Node2D
	spawner.call("spawn", actor.position.x)
	await physics(5)
	assert(game.get("state") == "dead" and bool(actor.get("dead")) and sprite.animation == &"death_right")
	assert(not music.get("players")[0].playing and int(game.get("audio")["death_sfx"].get("triggers")) > 0)
	await physics(35)
	assert((hud.get("overlay") as Control).visible and hud.get("display_mode") == "over")
	var best: int = int(game.get("best"))
	assert(best >= saved_score)
	(hud.get("primary") as Button).pressed.emit()
	await physics(3)
	assert(game.get("state") == "running" and not bool(actor.get("dead")) and int(game.get("score")) <= 2)
	assert(spawner.get("obstacles").is_empty())
	game.queue_free()
	await process_frame
	assert(AudioServer.bus_count == buses)
	var recreated: Node2D = packed.instantiate() as Node2D
	root.add_child(recreated)
	await process_frame
	assert(int(recreated.get("best")) >= best)
	assert(float(recreated.get("mixer_values")["BGM"]) == -60.0)
	recreated.queue_free()
	await process_frame
	var file: FileAccess = FileAccess.open("res://runtime-proof.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"ready_template": true, "jump_and_no_double_jump": true, "collision_death_animation": true, "score_restart_best_persisted": true, "bgm_steps_sfx_buses": true, "pause_freezes_simulation": true, "volume_persisted": true, "buses_released": true}))
	file.close()
	print("ALI_GAME_KIT_OK")
	OS.delay_msec(250)
	await process_frame
	quit(0)
