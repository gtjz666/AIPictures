@tool
extends RefCounted
## Deterministic native resource builders. Source textures remain unchanged.


static func regions(texture: Texture2D, cell: Vector2i, margin: Vector2i, gap: Vector2i) -> Array[Rect2i]:
	var rows: Array[Rect2i] = []
	if texture == null or cell.x < 1 or cell.y < 1 or margin.x < 0 or margin.y < 0 or gap.x < 0 or gap.y < 0: return rows
	for y: int in range(margin.y,texture.get_height()-cell.y+1,cell.y+gap.y):
		for x: int in range(margin.x,texture.get_width()-cell.x+1,cell.x+gap.x):
			if rows.size() >= 16384: return []
			rows.append(Rect2i(Vector2i(x,y),cell))
	return rows


static func ordered(paths: PackedStringArray, reverse: bool = false) -> PackedStringArray:
	var result: Array[String] = []
	for path: String in paths: result.append(path)
	result.sort_custom(func(a: String,b: String) -> bool: return a.naturalnocasecmp_to(b) < 0)
	if reverse: result.reverse()
	return PackedStringArray(result)


static func frames(paths: PackedStringArray, options: Dictionary) -> Dictionary:
	var textures: Array[Texture2D] = []
	if paths.is_empty(): return {"error":"请选择图片序列或Sprite Sheet"}
	var sheet: bool = options.get("sheet",false)
	if sheet and paths.size() != 1: return {"error":"Sprite Sheet只选择一张图"}
	var sorted: PackedStringArray = ordered(paths,options.get("reverse",false)) if options.get("sort",true) else paths
	for path: String in sorted:
		if not path.begins_with("res://") or not ResourceLoader.exists(path): return {"error":"需要当前项目中的图片"}
		var texture: Texture2D = load(path) as Texture2D
		if texture == null: return {"error":"不是Texture2D："+path}
		if sheet:
			var boxes: Array[Rect2i] = regions(texture,options.get("cell",Vector2i(32,32)),options.get("margin",Vector2i.ZERO),options.get("gap",Vector2i.ZERO))
			var selection: Array = options.get("selection",[])
			for index: int in range(boxes.size()):
				if not selection.is_empty() and not index in selection: continue
				var atlas: AtlasTexture = AtlasTexture.new()
				atlas.atlas = texture
				atlas.region = Rect2(boxes[index])
				textures.append(atlas)
		else: textures.append(texture)
	if textures.is_empty() or textures.size() > 16384: return {"error":"没有有效帧或帧数超过16384"}
	if sheet and options.get("reverse",false): textures.reverse()
	var name: String = str(options.get("clip","default")).strip_edges()
	if name.is_empty() or ":" in name or "/" in name: return {"error":"动画名称不可为空或含路径符号"}
	var fps: float = float(options.get("fps",12))
	if fps <= 0 or fps > 240: return {"error":"帧率需在0–240之间"}
	var result: SpriteFrames = SpriteFrames.new()
	result.remove_animation("default")
	result.add_animation(name)
	result.set_animation_speed(name,fps)
	result.set_animation_loop(name,options.get("loop",true))
	for texture: Texture2D in textures: result.add_frame(name,texture)
	return {"resource":result,"count":textures.size()}


static func animation(frames: SpriteFrames, clip: String, target: String = "Visual") -> Animation:
	var result: Animation = Animation.new()
	var track: int = result.add_track(Animation.TYPE_VALUE)
	result.track_set_path(track,NodePath(target+":texture"))
	result.value_track_set_update_mode(track,Animation.UPDATE_DISCRETE)
	var fps: float = frames.get_animation_speed(clip)
	for index: int in range(frames.get_frame_count(clip)): result.track_insert_key(track,float(index)/fps,frames.get_frame_texture(clip,index))
	result.length = float(frames.get_frame_count(clip))/fps
	result.loop_mode = Animation.LOOP_LINEAR if frames.get_animation_loop(clip) else Animation.LOOP_NONE
	return result


static func tileset(path: String, options: Dictionary) -> Dictionary:
	if not path.begins_with("res://") or not ResourceLoader.exists(path): return {"error":"请选择项目内图集"}
	var texture: Texture2D = load(path) as Texture2D
	var cell: Vector2i = options.get("cell",Vector2i(32,32))
	var margin: Vector2i = options.get("margin",Vector2i.ZERO)
	var gap: Vector2i = options.get("gap",Vector2i.ZERO)
	var boxes: Array[Rect2i] = regions(texture,cell,margin,gap)
	if boxes.is_empty(): return {"error":"网格与图集尺寸不匹配"}
	var result: TileSet = TileSet.new()
	result.tile_size = cell
	var atlas: TileSetAtlasSource = TileSetAtlasSource.new()
	atlas.texture = texture
	atlas.texture_region_size = cell
	atlas.margins = margin
	atlas.separation = gap
	var selection: Array = options.get("selection",[])
	for index: int in range(boxes.size()):
		if not selection.is_empty() and not index in selection: continue
		var coords: Vector2i = (boxes[index].position-margin)/(cell+gap)
		atlas.create_tile(coords)
	if atlas.get_tiles_count() == 0: return {"error":"没有选择瓦片"}
	result.add_source(atlas,0)
	return {"resource":result,"count":atlas.get_tiles_count()}


static func save(resource: Resource, path: String) -> String:
	if not path.begins_with("res://") or ".." in path or path.get_extension() != "tres": return "请选择项目内新的.tres文件"
	if FileAccess.file_exists(path): return "文件已存在，请使用新名称"
	return "" if ResourceSaver.save(resource,path) == OK else "资源保存失败"
