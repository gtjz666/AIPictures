extends SceneTree


func _initialize() -> void:
	run.call_deferred()


func picture(name: String) -> void:
	await process_frame
	await process_frame
	RenderingServer.force_draw()
	assert(root.get_texture().get_image().save_png("res://" + name + ".png") == OK)


func run() -> void:
	root.size = Vector2i(960, 540)
	var game: Node2D = (load("res://runner_game.tscn") as PackedScene).instantiate() as Node2D
	var data: Dictionary = game.get("game_blueprint").duplicate(true)
	data["nodes"][1]["params"]["save_key"] = "render_" + str(Time.get_ticks_usec())
	game.set("game_blueprint", data)
	root.add_child(game)
	await picture("game-start")
	game.call("event", "input", 1)
	game.get("spawner").call("spawn", 600)
	for index: int in range(8):
		await physics_frame
	await picture("game-running")
	game.call("event", "input", 3)
	(game.get("hud").get("settings_panel") as Control).show()
	await picture("game-audio")
	game.call("event", "input", 3)
	game.call("event", "spawner", 0)
	for index: int in range(40):
		await physics_frame
	await picture("game-over")
	game.queue_free()
	await process_frame
	print("ALI_GAME_RENDER_OK")
	OS.delay_msec(250)
	quit(0)
