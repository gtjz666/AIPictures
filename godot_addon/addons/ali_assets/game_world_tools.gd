@tool
extends Node
## Native 2D world adapters. TileSet owns terrain/collision; only cells change.
const Access: GDScript = preload("blueprint_access.gd")
const Task: GDScript = preload("blueprint_task.gd")
const Link: GDScript = preload("resource_link.gd")
var game: Node
var owned: Dictionary = {}
var layers: Dictionary = {}
var changes: Dictionary = {}
var batches: Array[Dictionary] = []
var following: Dictionary = {}


func setup(controller: Node) -> void:
	game = controller
	process_mode = Node.PROCESS_MODE_ALWAYS
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] == "tilemap": bind_layer(node["params"])


func result(error: String = "", value: Variant = null) -> RefCounted:
	var task: RefCounted = Task.new()
	task.call("finish", "completed" if error.is_empty() else "failed", value, error)
	return task


func publish(id: String, value: Variant, context: Dictionary) -> void:
	game.get("features").get("values")[id] = value
	if not context.has("values"): context["values"] = {}
	context["values"][id] = value


func execute(node: Dictionary, port: int, context: Dictionary) -> RefCounted:
	var p: Dictionary = node["params"]
	var id: String = str(node["id"])
	match str(node["kind"]):
		"background": return background(id, p, port, context)
		"scene_object": return scene_object(id, p, port, context)
		"camera2d": return camera(p, port)
		"tilemap": return tilemap(id, p, context)
	return result("未知场景适配器")


func object_for(id: String, p: Dictionary) -> Node:
	var target: Node = Access.node(game, p.get("target", ""))
	if target != null: return target
	return owned.get(id) as Node if is_instance_valid(owned.get(id)) else null


func object_command(id: String, target: Node, port: int) -> RefCounted:
	if target == null: return result("场景物体不存在")
	if port == 3:
		if owned.get(id) != target: return result("删除仅针对本模块创建的对象；绑定对象可用显示／隐藏")
		if target.get_parent() is Parallax2D and target.get_parent().get_parent() == self: target.get_parent().queue_free()
		else: target.queue_free()
		owned.erase(id)
	elif target is CanvasItem:
		(target as CanvasItem).visible = port == 1
	return result()


func background(id: String, p: Dictionary, port: int, context: Dictionary) -> RefCounted:
	var target: Node = object_for(id, p)
	if port > 0: return object_command(id, target, port)
	if str(p["image"]).is_empty(): return result("请选择背景图片")
	var sprite: Sprite2D = target as Sprite2D
	var parallax: Parallax2D
	if sprite == null and target != null: return result("背景绑定目标需要Sprite2D")
	if sprite == null:
		sprite = Sprite2D.new()
		sprite.name = str(p["name"])
		if p["parallax"]:
			parallax = Parallax2D.new()
			parallax.name = str(p["name"]) + "Parallax"
			add_child(parallax)
			parallax.add_child(sprite)
		else: add_child(sprite)
		owned[id] = sprite
	elif sprite.get_parent() is Parallax2D: parallax = sprite.get_parent() as Parallax2D
	if p["parallax"] and parallax == null: return result("已绑定Sprite2D需置于原生Parallax2D中，或留空目标自动创建")
	sprite.texture = load(str(p["image"])) as Texture2D
	sprite.centered = false
	sprite.position = Vector2(float(p["x"]), float(p["y"]))
	sprite.rotation_degrees = float(p["rotation"])
	sprite.modulate.a = float(p["alpha"])
	sprite.z_index = int(p["layer"])
	var size: Vector2 = sprite.texture.get_size()
	sprite.scale = Vector2(float(p["width"]) / size.x if float(p["width"]) > 0 else 1.0, float(p["height"]) / size.y if float(p["height"]) > 0 else 1.0)
	if parallax != null:
		parallax.scroll_scale = Vector2(float(p["ratio_x"]), float(p["ratio_y"]))
		parallax.autoscroll = Vector2(float(p["scroll_x"]), float(p["scroll_y"]))
		parallax.repeat_size = Vector2(float(p["repeat_x"]), float(p["repeat_y"]))
	else:
		sprite.region_enabled = float(p["repeat_x"]) > 0 or float(p["repeat_y"]) > 0
		sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
		sprite.region_rect = Rect2(Vector2.ZERO, Vector2(float(p["repeat_x"]) if float(p["repeat_x"]) > 0 else size.x, float(p["repeat_y"]) if float(p["repeat_y"]) > 0 else size.y))
	publish(id, sprite, context)
	return result()


func scene_object(id: String, p: Dictionary, port: int, context: Dictionary) -> RefCounted:
	var target: Node = object_for(id, p)
	if port in [1,2,3]: return object_command(id, target, port)
	if port == 4:
		var animated: AnimatedSprite2D = target as AnimatedSprite2D
		if animated == null and target != null:
			var sprites: Array[Node] = target.find_children("*","AnimatedSprite2D",true,false)
			if not sprites.is_empty(): animated = sprites[0] as AnimatedSprite2D
		if animated != null: return game.get("animations").call("start", {"mode":"frames","clip":p["clip"],"loops":1}, animated) as RefCounted
		var player: AnimationPlayer = target as AnimationPlayer
		if player == null and target != null:
			var players: Array[Node] = target.find_children("*","AnimationPlayer",true,false)
			if not players.is_empty(): player = players[0] as AnimationPlayer
		return game.get("animations").call("start",{"mode":"animation","clip":p["clip"],"loops":1},player) as RefCounted if player != null else result("目标无AnimatedSprite2D或AnimationPlayer")
	if target == null:
		if str(p["resource"]).is_empty(): return result("请选择场景物体资源")
		var resource: Resource = load(str(p["resource"]))
		if p["kind"] == "image" and resource is Texture2D:
			var sprite: Sprite2D = Sprite2D.new()
			sprite.texture = resource as Texture2D
			target = sprite
		elif p["kind"] == "frames" and Link.frames(resource) != null:
			var sprite: AnimatedSprite2D = AnimatedSprite2D.new()
			sprite.sprite_frames = Link.frames(resource).duplicate(true) as SpriteFrames
			target = sprite
		elif p["kind"] == "scene" and resource is PackedScene:
			target = (resource as PackedScene).instantiate()
			if not target is Node2D and not target is Control:
				target.free()
				return result("当前场景物体支持Node2D／Control根节点")
		else: return result("所选资源与物体类型不符")
		if p["collision"] and not target is CollisionObject2D and target is Node2D:
			var body: StaticBody2D = StaticBody2D.new()
			target.name = "Visual"
			body.add_child(target)
			var collision: CollisionShape2D = CollisionShape2D.new()
			var shape: RectangleShape2D = RectangleShape2D.new()
			shape.size = Vector2(float(p["width"]), float(p["height"]))
			collision.shape = shape
			body.add_child(collision)
			target = body
		target.name = str(p["name"])
		add_child(target, true)
		owned[id] = target
	if target is Node2D:
		(target as Node2D).position = Vector2(float(p["x"]), float(p["y"]))
		(target as Node2D).scale = Vector2(float(p["scale_x"]), float(p["scale_y"]))
		(target as Node2D).rotation_degrees = float(p["rotation"])
		(target as Node2D).z_index = int(p["layer"])
	elif target is Control:
		(target as Control).position = Vector2(float(p["x"]), float(p["y"]))
		(target as Control).scale = Vector2(float(p["scale_x"]), float(p["scale_y"]))
		(target as Control).rotation_degrees = float(p["rotation"])
		(target as Control).z_index = int(p["layer"])
	publish(id, target, context)
	game.get("features").call("bind_signals")
	game.get("program").call("bind_signals")
	return result()


func bind_layer(p: Dictionary) -> TileMapLayer:
	var key: String = str(p["save_key"])
	var layer: TileMapLayer = Access.node(game, p["target"]) as TileMapLayer
	var created: bool = false
	if layer == null and is_instance_valid(layers.get(key)): layer = layers[key] as TileMapLayer
	if layer == null and str(p["target"]).is_empty():
		layer = TileMapLayer.new()
		created = true
		layer.name = str(p["name"])
		add_child(layer, true)
	if layer == null: return null
	if not str(p["tileset"]).is_empty(): layer.tile_set = load(str(p["tileset"])) as TileSet
	if created or p["operation"] == "bind":
		layer.z_index = int(p["layer"])
		layer.collision_enabled = bool(p["collision"])
	layers[key] = layer
	if not changes.has(key): changes[key] = {}
	return layer


func cell_data(layer: TileMapLayer, at: Vector2i) -> Dictionary:
	var atlas: Vector2i = layer.get_cell_atlas_coords(at)
	return {"x":at.x,"y":at.y,"source":layer.get_cell_source_id(at),"atlas_x":atlas.x,"atlas_y":atlas.y,"alternative":layer.get_cell_alternative_tile(at)}


func record_cell(key: String, layer: TileMapLayer, at: Vector2i) -> void:
	changes[key][str(at.x) + "," + str(at.y)] = cell_data(layer, at)


func tilemap(id: String, p: Dictionary, context: Dictionary) -> RefCounted:
	var layer: TileMapLayer = bind_layer(p)
	if layer == null: return result("地图目标不是TileMapLayer或尚未创建")
	var operation: String = str(p["operation"])
	if operation == "bind": return result()
	if layer.tile_set == null: return result("TileMapLayer缺少TileSet")
	var key: String = str(p["save_key"])
	var point: Variant = game.get("program").call("input_value", id, 1, Vector2(float(p["x"]),float(p["y"])))
	if not point is Vector2: return result("地图坐标需要Vector2")
	var at: Vector2i = Vector2i(point)
	if operation == "enabled": layer.enabled = bool(p["enabled"]); return result()
	if operation in ["read","world_to_cell","cell_to_world"]:
		var data: Dictionary = cell_data(layer, at)
		if operation == "world_to_cell":
			var cell: Vector2i = layer.local_to_map(layer.to_local(point))
			data = {"x":cell.x,"y":cell.y}
		elif operation == "cell_to_world":
			var world: Vector2 = layer.to_global(layer.map_to_local(at))
			data = {"x":world.x,"y":world.y}
		publish(id, data, context)
		return result()
	if operation in ["set","fill"]:
		if not layer.tile_set.has_source(int(p["source"])): return result("TileSet没有所选瓦片源")
		var source: TileSetSource = layer.tile_set.get_source(int(p["source"]))
		if not source.has_tile(Vector2i(int(p["atlas_x"]),int(p["atlas_y"]))) or not source.has_alternative_tile(Vector2i(int(p["atlas_x"]),int(p["atlas_y"])),int(p["alternative"])): return result("图集格子或替代瓦片不存在")
	if operation == "set":
		layer.set_cell(at,int(p["source"]),Vector2i(int(p["atlas_x"]),int(p["atlas_y"])),int(p["alternative"]))
		record_cell(key, layer, at)
		return result()
	if operation == "erase":
		layer.erase_cell(at)
		record_cell(key,layer,at)
		return result()
	var cells: Array[Vector2i] = []
	if operation == "clear": cells.assign(layer.get_used_cells())
	else:
		for y: int in range(int(p["height"])):
			for x: int in range(int(p["width"])): cells.append(at + Vector2i(x,y))
	if cells.size() > 262144: return result("一次地图操作最多262144格")
	if operation == "terrain" and (int(p["terrain_set"]) >= layer.tile_set.get_terrain_sets_count() or int(p["terrain"]) >= layer.tile_set.get_terrains_count(int(p["terrain_set"]))): return result("TileSet未配置所选地形集合／地形；请先在Godot原生编辑器中配置")
	var task: RefCounted = Task.new()
	batches.append({"task":task,"layer":layer,"key":key,"p":p.duplicate(true),"cells":cells,"cursor":0,"touched":{}})
	return task


func camera(p: Dictionary, port: int) -> RefCounted:
	var camera_node: Camera2D = Access.node(game, p["target"]) as Camera2D
	if camera_node == null and str(p["target"]).is_empty():
		camera_node = game.get_viewport().get_camera_2d()
		if camera_node == null:
			camera_node = Camera2D.new()
			camera_node.name = "Camera2D"
			add_child(camera_node)
	if camera_node == null: return result("需要Camera2D目标")
	var id: int = camera_node.get_instance_id()
	if port == 1:
		following.erase(id)
		game.get("animations").call("command", camera_node, "stop")
		return result()
	var operation: String = str(p["operation"])
	if operation == "follow":
		var subject: Node2D = Access.node(game, p["follow"]) as Node2D
		if subject == null: return result("跟随目标需要Node2D")
		camera_node.position_smoothing_enabled = float(p["smoothing"]) > 0
		camera_node.position_smoothing_speed = maxf(0.01,float(p["smoothing"]))
		following[id] = {"camera":weakref(camera_node),"target":weakref(subject),"ui":bool(p["ui"])}
		return result()
	if operation == "stop_follow": following.erase(id); return result()
	if operation == "limits":
		if float(p["x"]) >= float(p["right"]) or float(p["y"]) >= float(p["bottom"]): return result("相机边界需要左小于右、上小于下")
		camera_node.limit_left = int(p["x"])
		camera_node.limit_top = int(p["y"])
		camera_node.limit_right = int(p["right"])
		camera_node.limit_bottom = int(p["bottom"])
		return result()
	if operation == "shake": return game.get("animations").call("shake",camera_node,float(p["strength"]),float(p["seconds"]),bool(p["ui"])) as RefCounted
	var property: String = "global_position"
	var destination: Variant = Vector2(float(p["x"]),float(p["y"]))
	if operation == "zoom":
		if destination.x <= 0 or destination.y <= 0: return result("相机缩放必须大于0")
		property = "zoom"
	elif operation == "rotate": property = "rotation_degrees"; destination = float(p["angle"])
	elif operation == "offset": property = "offset"
	elif operation == "current":
		var previous: Camera2D = game.get_viewport().get_camera_2d()
		if previous != null and previous != camera_node:
			destination = camera_node.global_position
			camera_node.global_position = previous.get_screen_center_position()
		else: destination = camera_node.global_position
		camera_node.make_current()
	return game.get("animations").call("start",{"mode":"property","property":property,"to":destination,"seconds":p["seconds"],"ui":p["ui"]},camera_node) as RefCounted


func export_changes() -> Dictionary:
	return changes.duplicate(true)


func restore_changes(data: Dictionary) -> String:
	for key: String in data:
		if not layers.has(key) or not is_instance_valid(layers[key]): return "存档地图尚未注册：" + key
		if not data[key] is Dictionary or data[key].size() > 262144: return "地图修改记录无效"
		for raw: Variant in data[key].values():
			if not raw is Dictionary: return "瓦片修改格式无效"
			for field: String in ["x","y","source","atlas_x","atlas_y","alternative"]:
				if not raw.has(field) or not (raw[field] is int or raw[field] is float) or not is_finite(float(raw[field])) or float(raw[field]) != int(raw[field]) or absf(float(raw[field])) > 1000000: return "瓦片修改包含无效数值"
			if int(raw["source"]) >= 0:
				var layer: TileMapLayer = layers[key] as TileMapLayer
				if layer.tile_set == null or not layer.tile_set.has_source(int(raw["source"])): return "存档引用的瓦片源不存在"
				var source: TileSetSource = layer.tile_set.get_source(int(raw["source"]))
				if not source.has_alternative_tile(Vector2i(int(raw["atlas_x"]),int(raw["atlas_y"])),int(raw["alternative"])): return "存档引用的瓦片不存在"
	for key: String in data:
		var layer: TileMapLayer = layers[key] as TileMapLayer
		for row: Dictionary in data[key].values(): layer.set_cell(Vector2i(int(row["x"]),int(row["y"])),int(row["source"]),Vector2i(int(row["atlas_x"]),int(row["atlas_y"])),int(row["alternative"]))
		changes[key] = data[key].duplicate(true)
	return ""


func _process(_delta: float) -> void:
	for key: Variant in following.keys():
		var row: Dictionary = following[key]
		var subject: Node2D = row["target"].get_ref() as Node2D
		var camera_node: Camera2D = row["camera"].get_ref() as Camera2D
		if subject == null or camera_node == null: following.erase(key); continue
		if game.get("state") != "paused" or row["ui"]: camera_node.global_position = subject.global_position
	for row: Dictionary in batches.duplicate():
		var task: RefCounted = row["task"]
		if task.get("state") != "running": batches.erase(row); continue
		if game.get("state") == "paused": continue
		var layer: TileMapLayer = row["layer"] as TileMapLayer
		if not is_instance_valid(layer): task.call("finish","failed",null,"地图图层已删除"); continue
		var p: Dictionary = row["p"]
		var selected: Array[Vector2i] = []
		var touched: Dictionary = {}
		var end: int = mini(int(row["cursor"])+1024,row["cells"].size())
		for index: int in range(int(row["cursor"]),end):
			var at: Vector2i = row["cells"][index]
			if p["operation"] == "terrain": selected.append(at)
			elif p["operation"] == "fill": layer.set_cell(at,int(p["source"]),Vector2i(int(p["atlas_x"]),int(p["atlas_y"])),int(p["alternative"]))
			else: layer.erase_cell(at)
			if p["operation"] == "terrain":
				for offset_y: int in range(-1,2):
					for offset_x: int in range(-1,2): touched[at+Vector2i(offset_x,offset_y)] = true
			else: touched[at] = true
		if not selected.is_empty(): layer.set_cells_terrain_connect(selected,int(p["terrain_set"]),int(p["terrain"]))
		for at: Vector2i in touched: record_cell(str(row["key"]),layer,at)
		row["cursor"] = end
		if end == row["cells"].size():
			task.call("finish")


func _exit_tree() -> void:
	for row: Dictionary in batches: row["task"].call("cancel")
	batches.clear()
	following.clear()
