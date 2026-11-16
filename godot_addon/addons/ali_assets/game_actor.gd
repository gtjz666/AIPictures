extends CharacterBody2D
## Adapted from the skill's typed platformer controller; fixed X for a runner.
var game: Node2D
var params: Dictionary
var sprite: AnimatedSprite2D
var start_position: Vector2
var running: bool = false
var dead: bool = false
var dying_time: float = 0.0
var footsteps: float = 0.0
var was_grounded: bool = false


func setup(controller: Node2D, settings: Dictionary, frames: SpriteFrames, start: Vector2) -> void:
	game = controller
	params = settings
	start_position = start
	position = start
	motion_mode = CharacterBody2D.MOTION_MODE_GROUNDED
	collision_layer = 1
	collision_mask = 1
	var collider: CollisionShape2D = CollisionShape2D.new()
	var shape: RectangleShape2D = RectangleShape2D.new()
	shape.size = Vector2(float(params["collision_width"]), float(params["collision_height"]))
	collider.shape = shape
	collider.position.y = -shape.size.y / 2
	add_child(collider)
	sprite = AnimatedSprite2D.new()
	sprite.sprite_frames = frames.duplicate(true) as SpriteFrames
	sprite.sprite_frames.set_animation_loop(str(params["walk"]), true)
	sprite.sprite_frames.set_animation_loop(str(params["jump"]), false)
	sprite.sprite_frames.set_animation_loop(str(params["death"]), false)
	var texture: Texture2D = frames.get_frame_texture(str(params["walk"]), 0)
	sprite.scale = Vector2.ONE * float(params["height"]) / maxf(1.0, texture.get_height())
	sprite.position.y = -float(params["height"]) / 2
	add_child(sprite)
	sprite.animation = str(params["walk"])
	sprite.frame = 0


func command(port: int) -> void:
	match port:
		0:
			position = start_position
			velocity = Vector2.ZERO
			running = true
			dead = false
			dying_time = 0.0
			footsteps = 0.0
			sprite.rotation = 0
			sprite.speed_scale = 1
			sprite.play(str(params["walk"]))
		1:
			if running and not dead and is_on_floor() and velocity.y >= -1.0 and game.get("state") == "running":
				velocity.y = float(params["jump_velocity"])
				sprite.play(str(params["jump"]))
				game.call("event", "runner", 0)
		2:
			if dead:
				return
			dead = true
			sprite.speed_scale = 1
			running = false
			velocity = Vector2.ZERO
			sprite.play(str(params["death"]))
			dying_time = 0.0
			for index: int in range(sprite.sprite_frames.get_frame_count(str(params["death"]))):
				dying_time += sprite.sprite_frames.get_frame_duration(str(params["death"]), index)
			dying_time = maxf(0.2, dying_time / maxf(0.01, sprite.sprite_frames.get_animation_speed(str(params["death"]))))
			game.call("event", "runner", 2)
		3:
			running = false
			sprite.stop()


func _physics_process(delta: float) -> void:
	if game == null or game.get("state") == "paused":
		return
	if dying_time > 0:
		dying_time -= delta
		if dying_time <= 0:
			game.call("event", "runner", 3)
	if dead:
		return
	velocity.y += float(params["gravity"]) * delta
	move_and_slide()
	var grounded: bool = is_on_floor()
	if grounded and not was_grounded and running:
		game.call("event", "runner", 1)
	if running and grounded:
		sprite.play(str(params["walk"]))
		footsteps -= delta
		if footsteps <= 0:
			game.call("event", "runner", 4)
			footsteps = float(params["step_interval"])
	was_grounded = grounded
