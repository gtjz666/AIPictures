extends Node2D
var game: Node2D
var params: Dictionary
var ground_y: float
var offset: float = 0.0
var active: bool = false
var background: Texture2D
var ground_texture: Texture2D


func setup(controller: Node2D, settings: Dictionary, width: float, height: float) -> void:
	game = controller
	params = settings
	ground_y = height * float(params["ground_ratio"])
	background = load(str(params["background"])) as Texture2D if not str(params["background"]).is_empty() else null
	ground_texture = load(str(params["ground"])) as Texture2D if not str(params["ground"]).is_empty() else null
	var floor_body: StaticBody2D = StaticBody2D.new()
	var collider: CollisionShape2D = CollisionShape2D.new()
	var shape: RectangleShape2D = RectangleShape2D.new()
	shape.size = Vector2(maxf(8192, width * 8), 100)
	collider.shape = shape
	floor_body.position = Vector2(width / 2, ground_y + 50)
	floor_body.add_child(collider)
	add_child(floor_body)
	queue_redraw()


func command(port: int) -> void:
	active = port == 0
	if active:
		offset = 0


func tick(delta: float, speed: float) -> void:
	if active:
		offset += delta * speed
	queue_redraw()


func _draw() -> void:
	if game == null:
		return
	var area: Vector2 = get_viewport_rect().size
	var width: float = maxf(area.x, float(game.get("base_size").x))
	var height: float = maxf(area.y, float(game.get("base_size").y))
	draw_rect(Rect2(0, 0, width, height), Color(str(params["sky"])))
	if background != null:
		var tile_width: float = ground_y * background.get_width() / maxf(1, background.get_height())
		var shift: float = fmod(offset * float(params["parallax"]), tile_width)
		for index: int in range(int(ceil(width / tile_width)) + 2):
			draw_texture_rect(background, Rect2(index * tile_width - shift, 0, tile_width, ground_y), false)
	else:
		for index: int in range(7):
			var x: float = fposmod(index * 210.0 - offset * 0.12, width + 240) - 120
			var y: float = 100.0 + (index % 3) * 45
			draw_rect(Rect2(x, y, 90, 18), Color("f6fbef"))
			draw_rect(Rect2(x + 22, y - 14, 42, 20), Color("f6fbef"))
	draw_rect(Rect2(0, ground_y, width, height - ground_y), Color(str(params["ground_color"])))
	if ground_texture != null:
		var tile_height: float = minf(100, height - ground_y)
		var tile_width: float = tile_height * ground_texture.get_width() / maxf(1, ground_texture.get_height())
		for index: int in range(int(ceil(width / tile_width)) + 2):
			draw_texture_rect(ground_texture, Rect2(index * tile_width - fmod(offset, tile_width), ground_y, tile_width, tile_height), false)
	if ground_texture == null:
		draw_rect(Rect2(0, ground_y, width, 5), Color("557369"))
		for index: int in range(int(width / 45) + 2):
			var x: float = index * 45 - fmod(offset, 45)
			draw_rect(Rect2(x, ground_y + 18 + (index % 2) * 8, 14, 3), Color("a5b99c"))
