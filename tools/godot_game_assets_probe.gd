extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")


func _initialize() -> void:
	run.call_deferred()


func run() -> void:
	assert(Model.frames_at("res://fixtures/character.tscn").get_frame_count(&"walk_right") == 2)
	var packed: PackedScene = load("res://kit_from_editor.tscn") as PackedScene
	var checks: Array = []
	for size: Vector2i in [Vector2i(960, 540), Vector2i(800, 600), Vector2i(540, 960)]:
		var game: Node2D = packed.instantiate() as Node2D
		var data: Dictionary = game.get("game_blueprint").duplicate(true)
		var screen: Dictionary = Model.by_kind(data, "screen")["params"]
		screen["width"] = size.x
		screen["height"] = size.y
		screen["aspect"] = "expand" if size.x == 800 else "keep"
		game.set("game_blueprint", data)
		root.add_child(game)
		await process_frame
		assert(bool(game.get("initialized")))
		assert(root.content_scale_size == size)
		assert(root.content_scale_aspect == Window.CONTENT_SCALE_ASPECT_EXPAND if size.x == 800 else root.content_scale_aspect == Window.CONTENT_SCALE_ASPECT_KEEP)
		assert(game.get("world").get("background") != null and game.get("world").get("ground_texture") != null)
		var actor: CharacterBody2D = game.get("actor") as CharacterBody2D
		assert(actor.get("sprite").sprite_frames.get_frame_count(&"death_right") == 3)
		var hud: CanvasLayer = game.get("hud") as CanvasLayer
		var style: StyleBox = (hud.get("primary") as Button).get_theme_stylebox("normal")
		assert(style is StyleBoxTexture and (style as StyleBoxTexture).texture.resource_path == "res://fixtures/button.png")
		var event: InputEventKey = InputEventKey.new()
		event.pressed = true
		event.physical_keycode = KEY_SPACE
		game.call("_unhandled_key_input", event)
		assert(game.get("state") == "waiting")
		event.physical_keycode = KEY_K
		game.call("_unhandled_key_input", event)
		assert(game.get("state") == "running")
		(hud.get("sliders")["SFX"] as HSlider).value = -23
		assert(float(game.get("mixer_values")["SFX"]) == -23)
		checks.append({"size": [size.x, size.y], "key_binding": true, "character_ui_background_audio_slots": true})
		game.queue_free()
		await process_frame
	var invalid: Dictionary = Model.preset()
	Model.by_kind(invalid, "input")["params"]["jump"] = KEY_R
	assert(not Model.validate(invalid).is_empty())
	invalid = Model.preset()
	Model.by_kind(invalid, "runner")["params"]["frames"] = "res://fixtures/button.png"
	assert(not Model.validate(invalid, true).is_empty())
	await logic_modules(packed)
	var file: FileAccess = FileAccess.open("res://assets-proof.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(checks))
	file.close()
	OS.delay_msec(250)
	await process_frame
	print("ALI_GAME_ASSETS_ASPECT_OK")
	quit(0)


func logic_modules(packed: PackedScene) -> void:
	var game: Node2D = packed.instantiate() as Node2D
	var data: Dictionary = game.get("game_blueprint").duplicate(true)
	for entry: Array in [["pulse", "timer"], ["gate", "branch"], ["fan", "sequence"], ["after", "delay"], ["allowed", "boolean"], ["counter", "custom"]]:
		data["nodes"].append(Model.module(str(entry[0]), str(entry[1]), 0, 0))
	Model.find(data, "pulse")["params"]["seconds"] = 0.1
	Model.find(data, "after")["params"]["seconds"] = 0.05
	Model.find(data, "allowed")["params"]["name"] = "allowed"
	Model.find(data, "counter")["params"]["script"] = "res://fixtures/counter.gd"
	for edge: Array in [["session",0,"pulse",0],["pulse",0,"gate",0],["allowed",0,"gate",1],["gate",0,"fan",0],["fan",0,"counter",0],["fan",1,"after",0],["after",0,"click",0]]:
		data["edges"].append({"from":edge[0],"from_port":edge[1],"to":edge[2],"to_port":edge[3]})
	assert(Model.validate(data, true).is_empty(), Model.validate(data, true))
	game.set("game_blueprint", data)
	root.add_child(game)
	await process_frame
	game.call("event", "input", 1)
	for index: int in range(30):
		await physics_frame
	assert(int(game.get_meta("calls", 0)) >= 3)
	assert(bool(game.get("variables")["called"]))
	assert(int(game.get("audio")["click"].get("triggers")) >= 2)
	game.get("variables")["allowed"] = false
	var before: int = int(game.get_meta("calls", 0))
	for index: int in range(15):
		await physics_frame
	assert(int(game.get_meta("calls", 0)) == before)
	game.call("event", "input", 3)
	game.get("variables")["allowed"] = true
	for index: int in range(15):
		await physics_frame
	assert(int(game.get_meta("calls", 0)) == before)
	game.call("event", "input", 3)
	for index: int in range(15):
		await physics_frame
	assert(int(game.get_meta("calls", 0)) > before)
	game.queue_free()
	await process_frame
