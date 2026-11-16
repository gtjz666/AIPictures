extends SceneTree


func _initialize() -> void:
	call_deferred("run")


func press(game: Node, key: int) -> void:
	var input: InputEventKey = InputEventKey.new()
	input.physical_keycode = key
	input.pressed = true
	game.call("_unhandled_key_input", input)


func run() -> void:
	var game: Node2D = (load("res://blueprint_basics.tscn") as PackedScene).instantiate()
	root.add_child(game)
	await process_frame
	assert(game.get("initialized"))
	press(game, KEY_SPACE)
	assert(game.get("state") == "running")
	var program: RefCounted = game.get("program")
	var hp_id: String = str(program.get("health").keys()[0])
	press(game, KEY_J)
	assert(program.get("health")[hp_id]["value"] == 90.0)
	press(game, KEY_J)
	assert(program.get("health")[hp_id]["value"] == 90.0)
	press(game, KEY_K)
	assert(program.get("health")[hp_id]["value"] == 100.0)
	press(game, KEY_F)
	assert(program.get("machines").values()[0]["current"] == "attack")
	game.call("_process", 0.5)
	assert(program.get("machines").values()[0]["current"] == "idle")
	press(game, KEY_ESCAPE)
	assert(game.get("state") == "paused")
	press(game, KEY_ESCAPE)
	assert(game.get("state") == "running")
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if not args.is_empty():
		await process_frame
		RenderingServer.force_draw()
		assert(root.get_texture().get_image().save_png(args[0]) == OK)
	game.queue_free()
	await process_frame
	print("ALI_DEPLOYED_PROGRAM_DEMO_OK: START / DAMAGE / COOLDOWN / HEAL / FSM / PAUSE")
	OS.delay_msec(250)
	quit()
