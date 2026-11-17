extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Library: GDScript = preload("res://addons/ali_assets/game_library.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
const Link: GDScript = preload("res://addons/ali_assets/resource_link.gd")


func _initialize() -> void:
	run.call_deferred()


func run() -> void:
	assert(Model.TITLES.size() == 71)
	assert(Model.validate(Model.preset(), true).is_empty())
	assert(Model.validate(Model.scene_preset(), true).is_empty())
	assert(not Link.problem("res://fixtures/button.png", "frames").is_empty())
	assert(not Link.problem("res://fixtures/tone.wav", "image").is_empty())
	assert(Link.problem("res://fixtures/button.png", "image").is_empty())
	assert(Link.problem("res://fixtures/tone.wav", "audio").is_empty())
	assert(not Link.project_path("C:/outside.png"))
	var frames: SpriteFrames = SpriteFrames.new()
	frames.add_frame(&"default", load("res://fixtures/button.png"))
	assert(ResourceSaver.save(frames, "res://fixtures/frames.tres") == OK)
	var animation: Animation = Animation.new()
	animation.length = 0.5
	var track: int = animation.add_track(Animation.TYPE_VALUE)
	animation.track_set_path(track, NodePath("Original:position"))
	animation.track_insert_key(track, 0, Vector2(20, 20))
	animation.track_insert_key(track, 0.5, Vector2(200, 100))
	var unsafe: int = animation.add_track(Animation.TYPE_METHOD)
	animation.track_set_path(unsafe, NodePath("Original"))
	animation.track_insert_key(unsafe, 0.1, {"method":"queue_free", "args":[]})
	assert(ResourceSaver.save(animation, "res://fixtures/movement.tres") == OK)
	var library: AnimationLibrary = AnimationLibrary.new()
	library.add_animation(&"move", animation)
	assert(ResourceSaver.save(library, "res://fixtures/library.tres") == OK)
	assert(Link.problem("res://fixtures/library.tres", "library").is_empty())
	assert(Link.problem("res://fixtures/library.tres", "resource").is_empty())
	var holder: Node2D = Node2D.new()
	var animated: AnimatedSprite2D = AnimatedSprite2D.new()
	animated.sprite_frames = frames
	holder.add_child(animated)
	animated.owner = holder
	var character: PackedScene = PackedScene.new()
	assert(character.pack(holder) == OK)
	assert(ResourceSaver.save(character, "res://fixtures/character.tscn") == OK)
	holder.free()
	assert(Link.problem("res://fixtures/character.tscn", "scene").is_empty())
	assert(Link.problem("res://fixtures/character.tscn", "frames").is_empty())
	assert(Link.problem("res://fixtures/movement.tres", "animation").is_empty())
	assert(not Link.problem("res://fixtures/button.png", "animation").is_empty())
	var tiles: TileSet = TileSet.new()
	assert(ResourceSaver.save(tiles, "res://fixtures/tiles.tres") == OK)
	assert(Link.problem("res://fixtures/tiles.tres", "tileset").is_empty())
	# Runtime ResourceSaver does not assign an editor UID automatically.
	assert(Link.resolve(Link.descriptor("res://fixtures/frames.tres")) == "res://fixtures/frames.tres")
	var generated: int = ResourceUID.create_id()
	assert(ResourceSaver.set_uid("res://fixtures/frames.tres", generated) == OK)
	ResourceUID.add_id(generated, "res://fixtures/frames.tres")
	var identity: Dictionary = Link.descriptor("res://fixtures/frames.tres")
	assert(not str(identity["uid"]).is_empty())
	# An actual native UID registry relocation, not a string-only path rewrite.
	assert(DirAccess.rename_absolute("res://fixtures/frames.tres", "res://fixtures/renamed_frames.tres") == OK)
	var uid: int = ResourceUID.text_to_id(identity["uid"])
	ResourceUID.set_id(uid, "res://fixtures/renamed_frames.tres")
	assert(Link.resolve(identity) == "res://fixtures/renamed_frames.tres")
	var moved: Dictionary = {"nodes":[{"params":{"frames":identity["path"]}, "resources":{"frames":identity}}]}
	assert(Link.normalize(moved)["nodes"][0]["params"]["frames"] == "res://fixtures/renamed_frames.tres")
	var override: Dictionary = moved.duplicate(true)
	override["nodes"][0]["params"]["frames"] = "res://fixtures/button.png"
	assert(Link.normalize(override)["nodes"][0]["params"]["frames"] == "res://fixtures/button.png")
	var missing: Dictionary = {"params":{"image":"res://fixtures/deleted.png"},"resources":{"image":{"path":"res://fixtures/deleted.png","uid":""}}} # lint:ignore res_path -- deliberately absent resource
	assert(not Link.metadata_problem(missing).is_empty())
	var graph: Dictionary = Model.scene_preset()
	var button: Dictionary = Model.module("test_button", "button", 600, 50)
	button["params"].merge({"normal_texture":"res://fixtures/button.png", "hover_texture":"res://fixtures/sky.png", "hover_sound":"res://fixtures/tone.wav", "click_sound":"res://fixtures/tone.wav"}, true)
	button["resources"] = {"normal_texture": Link.descriptor(button["params"]["normal_texture"])}
	var texture_button: Dictionary = Model.module("texture_button", "button", 600, 300)
	texture_button["params"].merge({"widget":"texture", "normal_texture":"res://fixtures/button.png", "x":300.0}, true)
	graph["nodes"].append_array([button, texture_button])
	for port: int in range(5):
		graph["nodes"].append(Model.module("log_" + str(port), "log", 950, port * 150))
		graph["edges"].append({"from":"test_button", "from_port":port,"to":"log_" + str(port),"to_port":0})
	assert(Library.compile(graph).has("data"))
	assert(Builder.create_scene(graph, "res://buttons.tscn").is_empty())
	# The scene contains a private runtime copy, not an addon script reference.
	var packed: PackedScene = load("res://buttons.tscn") as PackedScene
	var game: Node2D = packed.instantiate() as Node2D
	assert("_modules_" in str(game.get_script().resource_path))
	root.add_child(game)
	await process_frame
	assert(game.get("initialized"))
	var service: Node = game.get("widgets") as Node
	var native: Button = service.get("buttons")["test_button"] as Button
	assert(native.get_theme_stylebox("normal") is StyleBoxTexture)
	assert(native.get_theme_stylebox("hover").texture == load("res://fixtures/sky.png"))
	assert(native.get_theme_stylebox("disabled").texture == native.get_theme_stylebox("normal").texture)
	var textured: TextureButton = service.get("buttons")["texture_button"] as TextureButton
	assert(textured.texture_normal == textured.texture_disabled and textured.texture_hover == textured.texture_normal)
	native.mouse_entered.emit()
	native.button_down.emit()
	native.button_up.emit()
	native.pressed.emit()
	native.mouse_exited.emit()
	for port: int in range(5):
		assert(game.get("program").get("trace").any(func(row: Dictionary) -> bool: return row["node"] == "log_" + str(port)))
	assert((service.get("voices")["test_button"]["click"] as AudioStreamPlayer).playing)
	assert((service.get("voices")["test_button"]["hover"] as AudioStreamPlayer).bus == game.get("bus_names")["UI"])
	var trace_size: int = game.get("program").get("trace").size()
	service.call("command", "test_button", 1)
	native.pressed.emit()
	assert(game.get("program").get("trace").size() == trace_size)
	service.call("command", "test_button", 0)
	service.call("command", "test_button", 3)
	assert(not native.visible)
	service.call("command", "test_button", 2)
	assert(native.visible)
	service.call("command", "test_button", 4)
	assert(game.get("program").get("trace").size() > trace_size)
	trace_size = game.get("program").get("trace").size()
	# Send a native viewport mouse press/release, not only a signal emission.
	var motion: InputEventMouseMotion = InputEventMouseMotion.new()
	motion.position = native.get_global_transform_with_canvas() * (native.size / 2)
	root.push_input(motion, true)
	await process_frame
	for pressed: bool in [true, false]:
		var mouse: InputEventMouseButton = InputEventMouseButton.new()
		mouse.position = motion.position
		mouse.button_index = MOUSE_BUTTON_LEFT
		mouse.pressed = pressed
		root.push_input(mouse, true)
		await process_frame
	assert(game.get("program").get("trace").size() > trace_size)
	game.queue_free()
	await process_frame
	await create_timer(0.1).timeout
	# Existing native UI is restored when the adapter exits; layout is untouched.
	var bound_game: Node2D = packed.instantiate() as Node2D
	var existing: Button = Button.new()
	existing.name = "Existing"
	existing.text = "original"
	existing.position = Vector2(7, 9)
	existing.size = Vector2(230, 80)
	bound_game.add_child(existing)
	var bound: Dictionary = graph.duplicate(true)
	Model.find(bound, "test_button")["params"]["target"] = "Existing"
	bound_game.set("game_blueprint", bound)
	bound_game.set("compiled_blueprint", {})
	root.add_child(bound_game)
	await process_frame
	assert(bound_game.get("initialized"))
	assert(existing.position == Vector2(7, 9) and existing.size == Vector2(230, 80))
	var bound_service: Node = bound_game.get("widgets") as Node
	bound_service.queue_free()
	await process_frame
	assert(existing.text == "original" and not existing.has_theme_stylebox_override("normal"))
	bound_game.queue_free()
	await process_frame
	await create_timer(0.1).timeout
	# Fixed-fps headless frames outrun the native audio mixing thread.
	OS.delay_msec(250)
	var file: FileAccess = FileAccess.open("res://blueprint05-proof.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"legacy_presets":true,"module_count":Model.TITLES.size(),"typed_resources":true,"uid_relocation":true,"manual_path_precedence":true,"missing_identity":true,"self_contained_scene":true,"button_five_events":true,"button_audio_bus":true,"disabled_guard":true,"normal_state_fallback":true,"bound_layout_and_restore":true}, "\t"))
	file.close()
	quit.call_deferred(0)
