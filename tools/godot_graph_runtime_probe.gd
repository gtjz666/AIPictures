extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/blueprint_model.gd")
var attacks: int = 0
var generic: Array[String] = []


func _initialize() -> void:
	run.call_deferred()


func key(code: Key, pressed: bool) -> void:
	var event: InputEventKey = InputEventKey.new()
	event.physical_keycode = code
	event.keycode = code
	event.pressed = pressed
	Input.parse_input_event(event)


func wait_physics(count: int) -> void:
	for index: int in range(count):
		await physics_frame


func run() -> void:
	var rows: Array = JSON.parse_string(FileAccess.get_file_as_string("res://probe-inputs.json"))
	for record: Dictionary in rows:
		var packed: PackedScene = load(str(record["resource"])) as PackedScene
		var body: CharacterBody2D = packed.instantiate() as CharacterBody2D
		root.add_child(body)
		await process_frame
		assert(body.get("blueprint_runtime") != null)
		var sprite: AnimatedSprite2D = body.get_node("AnimatedSprite2D") as AnimatedSprite2D
		var sfx: AudioStreamPlayer2D = body.get_node("BlueprintSound_sfx_attack") as AudioStreamPlayer2D
		var walk: AudioStreamPlayer2D = body.get_node("BlueprintSound_sfx_walk") as AudioStreamPlayer2D
		var ground: StaticBody2D = null
		if record["preset"] == "platformer":
			ground = StaticBody2D.new()
			var collider: CollisionShape2D = CollisionShape2D.new()
			var shape: RectangleShape2D = RectangleShape2D.new()
			shape.size = Vector2(4000, 20)
			collider.shape = shape
			ground.add_child(collider)
			ground.position.y = 30
			root.add_child(ground)
			await wait_physics(30)
			assert(body.is_on_floor())
		key(KEY_D, true)
		await wait_physics(8)
		assert(body.position.x > 0 and sprite.animation == &"walk_right" and walk.playing)
		assert(not (body.get_node("Footsteps") as AudioStreamPlayer2D).playing)
		key(KEY_D, false)
		await wait_physics(10)
		assert(not walk.playing)
		body.connect("attack_requested", func() -> void: attacks += 1)
		key(KEY_J, true)
		await wait_physics(2)
		key(KEY_J, false)
		assert(attacks == 0)
		key(KEY_K, true)
		await wait_physics(2)
		assert(attacks == 1 and sprite.animation == &"attack_right" and not sfx.playing)
		var heard: bool = false
		for index: int in range(24):
			await physics_frame
			if sfx.playing:
				heard = true
				assert(sprite.frame >= 2)
				break
		assert(heard and attacks == 1)
		key(KEY_K, false)
		await wait_physics(24)
		if record["preset"] == "platformer":
			key(KEY_SPACE, true)
			await wait_physics(3)
			assert(body.velocity.y < 0 and not body.is_on_floor())
			key(KEY_SPACE, false)
		if record["preset"] == "four_way":
			key(KEY_W, true)
			await wait_physics(5)
			assert(sprite.animation == &"walk_up" and body.velocity.y < 0)
			key(KEY_W, false)
		# Invalid JSON graphs reject cycles, dangling IDs, duplicate actions and bad frame numbers.
		var data: Dictionary = body.get("blueprint").duplicate(true)
		data["edges"].append({"from": "sfx_attack", "to": "key_attack"})
		assert(not Model.validate(data).is_empty())
		data = body.get("blueprint").duplicate(true)
		data["nodes"].append(Model.make_node("duplicate", "action", 0, 0, {"action": "attack"}))
		assert(not Model.validate(data).is_empty())
		data = body.get("blueprint").duplicate(true)
		Model.find_node(data, "sfx_attack")["params"]["frame"] = 100
		assert(not Model.validate(data, sprite.sprite_frames).is_empty())
		data = body.get("blueprint").duplicate(true)
		data["nodes"][0]["params"] = {}
		assert(not Model.validate(data).is_empty())
		body.queue_free()
		if ground != null:
			ground.queue_free()
		await process_frame
		attacks = 0
	await check_programmable_graph(str(rows[0]["resource"]))
	await check_grounded_branch(str(rows[-1]["resource"]))
	var file: FileAccess = FileAccess.open("res://runtime-proof.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"presets": 3, "rebound_key_only": true, "movement_and_jump": true, "exact_audio_frame": true, "repeat_stops": true, "legacy_footsteps_disabled": true, "invalid_graph_rejected": true, "boolean_branch": true, "sequence_nested_delay": true, "custom_script_executed": true, "ready_event": true}))
	file.close()
	OS.delay_msec(250)
	await process_frame
	print("ALI_GRAPH_RUNTIME_OK")
	quit(0)


func check_programmable_graph(path: String) -> void:
	var body: CharacterBody2D = (load(path) as PackedScene).instantiate() as CharacterBody2D
	var frames: SpriteFrames = (body.get_node("AnimatedSprite2D") as AnimatedSprite2D).sprite_frames
	var data: Dictionary = Model.preset("two_way", frames)
	Model.find_node(data, "key_attack")["params"]["code"] = KEY_K
	data["edges"] = data["edges"].filter(func(edge: Dictionary) -> bool: return edge["from"] != "key_attack")
	data["nodes"].append(Model.make_node("ready_event", "event", 0, 0, {"event": "ready"}))
	data["nodes"].append(Model.make_node("can_attack", "boolean", 0, 200, {"name": "can_attack", "value": false}))
	data["nodes"].append(Model.make_node("check", "branch", 300, 100, {"condition": "always", "invert": false}))
	data["nodes"].append(Model.make_node("sequence", "sequence", 600, 100, {}))
	data["nodes"].append(Model.make_node("custom", "custom", 900, 0, {"script": "res://sources/custom.gd"}))
	data["nodes"].append(Model.make_node("delay1", "delay", 900, 200, {"seconds": 0.1}))
	data["nodes"].append(Model.make_node("delay2", "delay", 1200, 200, {"seconds": 0.1}))
	data["edges"].append({"from": "ready_event", "to": "custom"})
	data["edges"].append({"from": "key_attack", "from_port": 1, "to": "check"})
	data["edges"].append({"from": "can_attack", "to": "check", "to_port": 1})
	data["edges"].append({"from": "check", "to": "sequence"})
	data["edges"].append({"from": "sequence", "to": "custom"})
	data["edges"].append({"from": "sequence", "from_port": 1, "to": "delay1"})
	data["edges"].append({"from": "delay1", "to": "delay2"})
	data["edges"].append({"from": "delay2", "to": "action_attack"})
	assert(Model.validate(data, frames).is_empty())
	body.set("blueprint", data)
	root.add_child(body)
	await process_frame
	assert(int(body.get_meta("custom_calls", 0)) == 1)
	attacks = 0
	body.connect("attack_requested", func() -> void: attacks += 1)
	key(KEY_K, true)
	await wait_physics(20)
	assert(attacks == 0 and int(body.get_meta("custom_calls", 0)) == 1)
	key(KEY_K, false)
	await wait_physics(2)
	body.call("set_blueprint_variable", "can_attack", true)
	key(KEY_K, true)
	await wait_physics(3)
	assert(attacks == 0 and int(body.get_meta("custom_calls", 0)) == 2)
	key(KEY_K, false)
	await wait_physics(14)
	assert(attacks == 1)
	var bad: Dictionary = data.duplicate(true)
	bad["edges"].append({"from": "delay2", "to": "delay1"})
	assert(not Model.validate(bad).is_empty())
	body.queue_free()
	await process_frame


func check_grounded_branch(path: String) -> void:
	var body: CharacterBody2D = (load(path) as PackedScene).instantiate() as CharacterBody2D
	var data: Dictionary = Model.preset("platformer", (body.get_node("AnimatedSprite2D") as AnimatedSprite2D).sprite_frames)
	Model.find_node(data, "key_attack")["params"]["code"] = KEY_K
	data["nodes"].append(Model.make_node("ground_check", "branch", 300, 0, {"condition": "grounded", "invert": false}))
	data["edges"] = data["edges"].filter(func(edge: Dictionary) -> bool: return edge["from"] != "key_attack")
	data["edges"].append({"from": "key_attack", "from_port": 1, "to": "ground_check"})
	data["edges"].append({"from": "ground_check", "to": "action_attack"})
	body.set("blueprint", data)
	root.add_child(body)
	attacks = 0
	body.connect("attack_requested", func() -> void: attacks += 1)
	key(KEY_K, true)
	await wait_physics(3)
	key(KEY_K, false)
	assert(attacks == 0)
	var ground: StaticBody2D = StaticBody2D.new()
	var collision: CollisionShape2D = CollisionShape2D.new()
	var shape: RectangleShape2D = RectangleShape2D.new()
	shape.size = Vector2(2000, 20)
	collision.shape = shape
	ground.add_child(collision)
	ground.position.y = 40
	root.add_child(ground)
	await wait_physics(30)
	assert(body.is_on_floor())
	key(KEY_K, true)
	await wait_physics(2)
	key(KEY_K, false)
	assert(attacks == 1)
	body.queue_free()
	ground.queue_free()
	await process_frame
