extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
var game: Node2D
var tools: Node


func _initialize() -> void:
	run.call_deferred()


func node(kind: String, p: Dictionary, id: String = "operation") -> Dictionary:
	var data: Dictionary = Model.module(id,kind,0,0)
	data["params"].merge(p,true)
	return data


func wait_done(task: RefCounted) -> void:
	for frame: int in range(240):
		if task.get("state") != "running": return
		await process_frame
	assert(false,"World task did not settle")


func run() -> void:
	var texture: Image = Image.create(128,32,false,Image.FORMAT_RGBA8)
	texture.fill(Color("507e62"))
	assert(texture.save_png("res://fixtures/terrain.png") == OK)
	var atlas: TileSetAtlasSource = TileSetAtlasSource.new()
	atlas.texture = ImageTexture.create_from_image(texture)
	atlas.texture_region_size = Vector2i(16,16)
	var tiles: TileSet = TileSet.new()
	tiles.tile_size = Vector2i(16,16)
	tiles.add_physics_layer()
	tiles.set_physics_layer_collision_layer(0,1)
	tiles.add_terrain_set()
	tiles.set_terrain_set_mode(0,TileSet.TERRAIN_MODE_MATCH_SIDES)
	tiles.add_terrain(0)
	tiles.add_source(atlas,0)
	for mask: int in range(16):
		var at: Vector2i = Vector2i(mask % 8,mask / 8)
		atlas.create_tile(at)
		var data: TileData = atlas.get_tile_data(at,0)
		data.terrain_set = 0
		data.terrain = 0
		for bit: int in range(4): data.set_terrain_peering_bit([TileSet.CELL_NEIGHBOR_RIGHT_SIDE,TileSet.CELL_NEIGHBOR_BOTTOM_SIDE,TileSet.CELL_NEIGHBOR_LEFT_SIDE,TileSet.CELL_NEIGHBOR_TOP_SIDE][bit],0 if mask & (1 << bit) else -1)
		data.set_collision_polygons_count(0,1)
		data.set_collision_polygon_points(0,0,PackedVector2Array([Vector2(-8,-8),Vector2(8,-8),Vector2(8,8),Vector2(-8,8)]))
	assert(ResourceSaver.save(tiles,"res://fixtures/world_tiles.tres") == OK)
	var graph: Dictionary = Model.scene_preset()
	var definition: Dictionary = node("tilemap",{"tileset":"res://fixtures/world_tiles.tres","operation":"bind","save_key":"floor"},"map")
	graph["nodes"].append(definition)
	assert(Builder.create_scene(graph,"res://world_game.tscn").is_empty())
	game = (load("res://world_game.tscn") as PackedScene).instantiate() as Node2D
	var target: Node2D = Node2D.new()
	target.name = "Subject"
	game.add_child(target)
	var camera: Camera2D = Camera2D.new()
	camera.name = "Camera"
	game.add_child(camera)
	root.add_child(game)
	await process_frame
	tools = game.get("world_tools") as Node
	var layer: TileMapLayer = tools.get("layers")["floor"] as TileMapLayer
	assert(layer.tile_set != null and layer.collision_enabled)
	var context: Dictionary = {"messages":{},"values":{},"budget":{"left":512}}
	definition["params"].merge({"operation":"fill","width":8,"height":4},true)
	var fill: RefCounted = tools.call("execute",definition,0,context) as RefCounted
	await wait_done(fill)
	assert(fill.get("state") == "completed" and layer.get_used_cells().size() == 32)
	assert(layer.get_cell_tile_data(Vector2i.ZERO).get_collision_polygons_count(0) == 1)
	definition["params"]["operation"] = "erase"
	assert(tools.call("execute",definition,0,context).get("state") == "completed")
	assert(layer.get_cell_source_id(Vector2i.ZERO) == -1)
	var delta: Dictionary = tools.call("export_changes")
	layer.clear()
	assert(tools.call("restore_changes",JSON.parse_string(JSON.stringify(delta))) == "")
	assert(layer.get_used_cells().size() == 31 and layer.get_cell_source_id(Vector2i.ZERO) == -1)
	definition["params"].merge({"operation":"terrain","width":4,"height":4,"x":10},true)
	var terrain: RefCounted = tools.call("execute",definition,0,context) as RefCounted
	await wait_done(terrain)
	assert(terrain.get("state") == "completed")
	assert(layer.get_cell_tile_data(Vector2i(11,1)).terrain == 0)
	definition["params"].merge({"operation":"cell_to_world","x":2,"y":3},true)
	tools.call("execute",definition,0,context)
	var coordinates: Dictionary = context["values"]["map"]
	assert(Vector2(float(coordinates["x"]),float(coordinates["y"])) == layer.to_global(layer.map_to_local(Vector2i(2,3))))
	definition["params"].merge({"operation":"fill","width":128,"height":128,"x":100,"y":0},true)
	var batch: RefCounted = tools.call("execute",definition,0,context) as RefCounted
	await process_frame
	await process_frame
	batch.call("cancel")
	var count: int = layer.get_used_cells().size()
	assert(count > 32 and count < 16000)
	for frame: int in range(3): await process_frame
	assert(layer.get_used_cells().size() == count)
	assert(tools.call("export_changes")["floor"].size() >= count)
	var background: Dictionary = node("background",{"image":"res://fixtures/sky.png","parallax":true,"repeat_x":96.0,"scroll_x":20.0},"bg")
	assert(tools.call("execute",background,0,context).get("state") == "completed")
	var sprite: Sprite2D = context["values"]["bg"] as Sprite2D
	assert(sprite.get_parent() is Parallax2D and (sprite.get_parent() as Parallax2D).autoscroll.x == 20)
	var obj: Dictionary = node("scene_object",{"resource":"res://fixtures/button.png","collision":true},"object")
	assert(tools.call("execute",obj,0,context).get("state") == "completed")
	assert(context["values"]["object"] is StaticBody2D)
	var camera_node: Dictionary = node("camera2d",{"target":"Camera","operation":"move","x":80.0,"y":40.0,"seconds":0.1})
	var motion: RefCounted = tools.call("execute",camera_node,0,context) as RefCounted
	await wait_done(motion)
	assert(camera.global_position.is_equal_approx(Vector2(80,40)))
	camera_node["params"].merge({"operation":"zoom","x":1.5,"y":1.5},true)
	motion = tools.call("execute",camera_node,0,context) as RefCounted
	await wait_done(motion)
	assert(camera.zoom.is_equal_approx(Vector2(1.5,1.5)))
	camera_node["params"].merge({"operation":"follow","follow":"Subject","smoothing":5.0},true)
	tools.call("execute",camera_node,0,context)
	target.position = Vector2(120,40)
	await process_frame
	await process_frame
	assert(camera.global_position.is_equal_approx(target.global_position))
	camera_node["params"].merge({"operation":"shake","seconds":0.1},true)
	var original_offset: Vector2 = camera.offset
	motion = tools.call("execute",camera_node,0,context) as RefCounted
	await wait_done(motion)
	assert(camera.offset.is_equal_approx(original_offset))
	game.queue_free()
	await process_frame
	OS.delay_msec(250)
	var file: FileAccess = FileAccess.open("res://world-proof.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"native_tileset_collision":true,"fill_erase_read_and_delta_restore":true,"terrain_connect":true,"coordinate_conversion":true,"batched_cancel_keeps_delta":true,"native_parallax":true,"scene_object_collision":true,"camera_move_zoom_follow_shake_restore":true}))
	file.close()
	quit.call_deferred(0)
