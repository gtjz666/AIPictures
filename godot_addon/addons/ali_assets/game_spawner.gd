extends Node2D
var game: Node2D
var params: Dictionary
var actor: CharacterBody2D
var active: bool = false
var remaining: float = 1.5
var obstacles: Array[Area2D] = []
var rng: RandomNumberGenerator = RandomNumberGenerator.new()
var texture: Texture2D
var hits: int = 0
var passes: int = 0


func setup(controller: Node2D, settings: Dictionary, player: CharacterBody2D) -> void:
	game = controller
	params = settings
	actor = player
	rng.randomize()
	if not str(params["texture"]).is_empty():
		texture = load(str(params["texture"])) as Texture2D


func command(port: int) -> void:
	active = port == 0
	if active:
		for obstacle: Area2D in obstacles:
			obstacle.queue_free()
		obstacles.clear()
		remaining = 1.5
		hits = 0
		passes = 0


func tick(delta: float, speed: float) -> void:
	if not active:
		return
	remaining -= delta
	if remaining <= 0:
		spawn()
		remaining = rng.randf_range(float(params["interval_min"]), float(params["interval_max"]))
		if params["fair_spacing"]:
			var flight: float = -2.0 * float(actor.get("params")["jump_velocity"]) / float(actor.get("params")["gravity"])
			remaining = maxf(remaining, flight + float(params["width"]) / speed + 0.3)
	for obstacle: Area2D in obstacles.duplicate():
		obstacle.position.x -= speed * delta
		if not obstacle.get_meta("passed", false) and obstacle.position.x + float(params["width"]) / 2 < actor.position.x:
			obstacle.set_meta("passed", true)
			passes += 1
			game.call("event", "spawner", 1)
		if obstacle.position.x < -200:
			obstacles.erase(obstacle)
			obstacle.queue_free()


func spawn(at_x: float = -1.0) -> Area2D:
	var obstacle: Area2D = Area2D.new()
	var height: float = float(params["height"])
	if params["fair_spacing"]:
		var jump: float = float(actor.get("params")["jump_velocity"])
		height = minf(height, jump * jump / (2.0 * float(actor.get("params")["gravity"])) * 0.7)
	var width: float = float(params["width"])
	var collider: CollisionShape2D = CollisionShape2D.new()
	var shape: RectangleShape2D = RectangleShape2D.new()
	shape.size = Vector2(width, height)
	collider.shape = shape
	obstacle.collision_layer = 2
	obstacle.collision_mask = 1
	obstacle.add_child(collider)
	if texture != null:
		var sprite: Sprite2D = Sprite2D.new()
		sprite.texture = texture
		sprite.scale = Vector2(width / texture.get_width(), height / texture.get_height())
		obstacle.add_child(sprite)
	else:
		var polygon: Polygon2D = Polygon2D.new()
		polygon.polygon = PackedVector2Array([Vector2(-width/2,-height/2),Vector2(width/2,-height/2),Vector2(width/2,height/2),Vector2(-width/2,height/2)])
		polygon.color = Color("458a78")
		obstacle.add_child(polygon)
	var viewport_width: float = maxf(float(game.get("base_size").x), get_viewport_rect().size.x)
	obstacle.position = Vector2(viewport_width + 100 if at_x < 0 else at_x, float(game.get("ground_y")) - height / 2)
	obstacle.body_entered.connect(func(body: Node2D) -> void:
		if body == actor and active and game.get("state") == "running":
			hits += 1
			game.call("event", "spawner", 0))
	add_child(obstacle)
	obstacles.append(obstacle)
	return obstacle
