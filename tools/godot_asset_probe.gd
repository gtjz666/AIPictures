extends SceneTree

func _initialize() -> void:
	run.call_deferred()


func run() -> void:
	var records: Array = JSON.parse_string(FileAccess.get_file_as_string("res://probe-inputs.json"))
	var checked: int = 0
	for record: Dictionary in records:
		var packed: PackedScene = load(str(record["resource"])) as PackedScene
		assert(packed != null)
		var node: Node = packed.instantiate()
		root.add_child(node)
		await process_frame
		await physics_frame
		await physics_frame
		var preset: String = str(record["preset"])
		if preset == "platformer":
			await check_platformer(node as CharacterBody2D)
		elif preset in ["two_way", "four_way"]:
			var body: CharacterBody2D = node as CharacterBody2D
			body.set("use_project_actions", true)
			var sprite: AnimatedSprite2D = body.get_node("AnimatedSprite2D") as AnimatedSprite2D
			var audio: AudioStreamPlayer2D = body.get_node("Footsteps") as AudioStreamPlayer2D
			assert(audio.stream != null)
			Input.action_press("ui_right")
			for frame: int in range(5):
				await physics_frame
			assert(body.position.x > 0.0 and sprite.animation == &"walk_right")
			assert(audio.playing)
			Input.action_release("ui_right")
			Input.action_press("ui_left" if preset == "two_way" else "ui_up")
			for frame: int in range(15):
				await physics_frame
			assert(sprite.flip_h if preset == "two_way" else sprite.animation == &"walk_up")
			Input.action_release("ui_left" if preset == "two_way" else "ui_up")
			for frame: int in range(15):
				await physics_frame
			assert(not audio.playing and body.velocity.length() < 0.01)
			assert(sprite.animation == &"idle_right" or not sprite.is_playing())
		elif preset == "audio":
			var sound: AudioStreamPlayer2D = node as AudioStreamPlayer2D
			assert(sound.stream.get_length() > 0.0)
		elif preset == "image":
			assert((node.get_node("Sprite2D") as Sprite2D).texture != null)
		else:
			assert((node.get_node("AnimatedSprite2D") as AnimatedSprite2D).sprite_frames.get_frame_count(&"default") == 8)
		node.queue_free()
		await process_frame
		checked += 1
	var script: GDScript = load("res://addons/ali_assets/asset_drag.gd") as GDScript
	var drag_button: Button = script.new()
	drag_button.set("resource_path", str(records[0]["resource"]))
	var data: Dictionary = drag_button.call("asset_drag_data")
	assert(data["type"] == "files" and data["files"][0] == records[0]["resource"])
	drag_button.free()
	print("ALI_ASSET_RUNTIME_OK ", checked)
	OS.delay_msec(250)
	await process_frame
	quit.call_deferred(0)


func key(code: Key, pressed: bool) -> void:
	var event: InputEventKey = InputEventKey.new()
	event.physical_keycode = code
	event.pressed = pressed
	Input.parse_input_event(event)
	Input.flush_buffered_events()


func check_platformer(body: CharacterBody2D) -> void:
	body.set("key_attack", KEY_J)
	var floor_body: StaticBody2D = StaticBody2D.new()
	var collision: CollisionShape2D = CollisionShape2D.new()
	var shape: RectangleShape2D = RectangleShape2D.new()
	shape.size = Vector2(2000.0, 16.0)
	collision.shape = shape
	floor_body.add_child(collision)
	floor_body.position.y = 24.0
	root.add_child(floor_body)
	for frame: int in range(20):
		await physics_frame
	assert(body.is_on_floor())
	body.set("key_right", KEY_L)
	key(KEY_L, true)
	key(KEY_SHIFT, true)
	for frame: int in range(20):
		await physics_frame
	var sprite: AnimatedSprite2D = body.get_node("AnimatedSprite2D") as AnimatedSprite2D
	assert(body.velocity.x > float(body.get("speed")) and sprite.animation == &"run_right")
	key(KEY_L, false)
	key(KEY_SHIFT, false)
	var previous_y: float = body.position.y
	key(KEY_SPACE, true)
	for frame: int in range(3):
		await physics_frame
	assert(body.position.y < previous_y and sprite.animation == &"jump_right")
	key(KEY_SPACE, false)
	var attacks: Array[bool] = [false]
	body.connect("attack_requested", func() -> void: attacks[0] = true)
	body.set("key_attack", KEY_K)
	key(KEY_K, true)
	for frame: int in range(2):
		await physics_frame
	assert(attacks[0] and sprite.animation == &"attack_right")
	key(KEY_K, false)
	body.call("take_damage")
	assert(sprite.animation == &"hurt_right")
	body.call("die")
	assert(bool(body.get("dead")) and sprite.animation == &"death_right")
	floor_body.queue_free()
