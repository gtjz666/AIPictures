@tool
extends RefCounted

const Importer: GDScript = preload("asset_import.gd")
const Drop: GDScript = preload("asset_drop.gd")
const Link: GDScript = preload("resource_link.gd")
const IMAGE_EXTENSIONS: Array[String] = ["png", "jpg", "jpeg", "webp"]
const MAX_FRAMES: int = 2048
const TRACKS: String = "res://generated/ali_assets/tracks"


static func acceptable(paths: PackedStringArray) -> bool:
	if paths.is_empty() or paths.size() > MAX_FRAMES: return false
	if paths.size() == 1:
		var path: String = paths[0]
		var ext: String = path.get_extension().to_lower()
		return ext in ["zip","json","tres","res","tscn"] or ext in IMAGE_EXTENSIONS or DirAccess.dir_exists_absolute(path)
	for path: String in paths:
		if not path.get_extension().to_lower() in IMAGE_EXTENSIONS: return false
	return true


static func from_payload(payload: Variant) -> PackedStringArray:
	if payload is Dictionary and payload.get("type") == "files":
		return PackedStringArray(payload.get("files", []))
	var path: String = Drop.from_drag(payload)
	return PackedStringArray([path]) if not path.is_empty() else PackedStringArray()


static func read(paths: PackedStringArray) -> Dictionary:
	if not acceptable(paths): return {"error":"拖入动画 ZIP、包含帧的文件夹、图片序列或 SpriteFrames。"}
	var path: String = paths[0]
	if paths.size() == 1:
		if DirAccess.dir_exists_absolute(path):
			var manifest: String = path.path_join("animation.json")
			if FileAccess.file_exists(manifest): return from_manifest(manifest)
			var images: PackedStringArray = []
			for name: String in DirAccess.get_files_at(path):
				if name.get_extension().to_lower() in IMAGE_EXTENSIONS: images.append(path.path_join(name))
			return decode_images(Importer.ordered(images), {}, null, path.get_file())
		match path.get_extension().to_lower():
			"zip": return from_zip(path)
			"json": return from_manifest(path)
			"tres", "res", "tscn":
				var resource_path: String = Drop.project_file(path)
				if resource_path.is_empty() or not ResourceLoader.exists(resource_path): return {"error":"请把 Godot 原生资源放在当前项目内。"}
				var frames: SpriteFrames = Link.frames(load(resource_path))
				if Drop.clips(frames).is_empty(): return {"error":"资源中没有可播放的 SpriteFrames。"}
				return {"frames":frames,"clip":Drop.clips(frames)[0]}
		var sidecar: String = path.get_basename() + ".json"
		if FileAccess.file_exists(sidecar):
			var parsed: Dictionary = metadata(sidecar)
			if parsed.get("sheet") == path.get_file(): return from_manifest(sidecar)
	return decode_images(Importer.ordered(paths), {}, null, path.get_file().get_basename())


static func metadata(path: String) -> Dictionary:
	var file: FileAccess = FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() > 2 * 1024 * 1024: return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	return parsed if parsed is Dictionary else {}


static func frame_rows(info: Dictionary, image_key: String) -> PackedStringArray:
	var images: PackedStringArray = []
	var rows: Variant = info.get("frames")
	if not rows is Array or rows.is_empty() or rows.size() > MAX_FRAMES: return images
	for row: Variant in rows:
		if not row is Dictionary or not safe_image(str(row.get(image_key, ""))): return PackedStringArray()
		images.append(str(row[image_key]))
	return images


static func safe_image(name: String) -> bool:
	return name == name.get_file() and not name.contains(":") and not name.contains("\\") and name.get_extension().to_lower() in IMAGE_EXTENSIONS


static func from_manifest(path: String) -> Dictionary:
	var info: Dictionary = metadata(path)
	var sheet: String = str(info.get("sheet", ""))
	if not sheet.is_empty():
		if not safe_image(sheet): return {"error":"图集文件名无效。"}
		var image: Image = Image.load_from_file(path.get_base_dir().path_join(sheet))
		var rows: Variant = info.get("frames")
		if image == null or image.is_empty() or not rows is Array or rows.is_empty() or rows.size() > MAX_FRAMES:
			return {"error":"图集或切片描述无效。"}
		var source: Texture2D = ImageTexture.create_from_image(image)
		var textures: Array[Texture2D] = []
		for row: Variant in rows:
			var rect: Variant = row.get("rect") if row is Dictionary else null
			if not rect is Dictionary or not ["x","y","w","h"].all(func(key: String) -> bool: return typeof(rect.get(key)) in [TYPE_INT, TYPE_FLOAT]):
				return {"error":"图集切片坐标无效。"}
			var box: Rect2i = Rect2i(int(rect.x),int(rect.y),int(rect.w),int(rect.h))
			if box.size.x <= 0 or box.size.y <= 0 or not Rect2i(Vector2i.ZERO,image.get_size()).encloses(box):
				return {"error":"图集切片超出图片。"}
			var atlas: AtlasTexture = AtlasTexture.new()
			atlas.atlas = source
			atlas.region = Rect2(box)
			textures.append(atlas)
		return assemble(textures,info,sheet.get_basename())
	var frames: PackedStringArray = frame_rows(info, "image")
	var paths: PackedStringArray = []
	for name: String in frames: paths.append(path.get_base_dir().path_join(name))
	return decode_images(paths,info,null,path.get_base_dir().get_file())


static func from_zip(path: String) -> Dictionary:
	var reader: ZIPReader = ZIPReader.new()
	if reader.open(path) != OK: return {"error":"无法打开动画 ZIP。"}
	var info: Variant = JSON.parse_string(reader.read_file("animation.json").get_string_from_utf8()) if reader.file_exists("animation.json") else {}
	var result: Dictionary
	if not info is Dictionary:
		result = {"error":"动画 ZIP 的描述文件无效。"}
	else:
		var paths: PackedStringArray = frame_rows(info, "image")
		if info.is_empty():
			for name: String in reader.get_files():
				if safe_image(name): paths.append(name)
			paths = Importer.ordered(paths)
		result = decode_images(paths,info,reader,path.get_file().get_basename())
	reader.close()
	return result


static func decode_images(paths: PackedStringArray, info: Dictionary, archive: ZIPReader, name: String) -> Dictionary:
	if paths.is_empty() or paths.size() > MAX_FRAMES: return {"error":"动画需包含 1–2048 张有效图片。"}
	var textures: Array[Texture2D] = []
	var pixels: int = 0
	for path: String in paths:
		var frame: Image
		if archive == null:
			frame = Image.load_from_file(path)
		else:
			var payload: PackedByteArray = archive.read_file(path)
			frame = Image.new()
			match path.get_extension().to_lower():
				"png": frame.load_png_from_buffer(payload)
				"webp": frame.load_webp_from_buffer(payload)
				_: frame.load_jpg_from_buffer(payload)
		if frame == null or frame.is_empty(): return {"error":"无法读取动画帧 " + path.get_file()}
		pixels += frame.get_width() * frame.get_height()
		if pixels > 96_000_000: return {"error":"这些帧的像素总量过大，请按动作拆成较短片段。"}
		textures.append(ImageTexture.create_from_image(frame))
	return assemble(textures,info,name)


static func assemble(textures: Array[Texture2D], info: Dictionary, name: String) -> Dictionary:
	var clip: String = str(info.get("clip",name)).validate_node_name().replace("/", "_").strip_edges()
	if clip.is_empty(): clip = "clip"
	var fps: float = float(info.get("fps",12)) if typeof(info.get("fps")) in [TYPE_FLOAT, TYPE_INT] else 12.0
	if not is_finite(fps) or fps <= 0 or fps > 240: return {"error":"动画帧率超出 0–240 FPS。"}
	var frames: SpriteFrames = SpriteFrames.new()
	frames.remove_animation("default")
	frames.add_animation(clip)
	frames.set_animation_speed(clip,fps)
	frames.set_animation_loop(clip,info.get("loop",false) == true)
	for frame: Texture2D in textures: frames.add_frame(clip,frame)
	return {"frames":frames,"clip":clip}


static func save(frames: SpriteFrames) -> String:
	if DirAccess.make_dir_recursive_absolute(TRACKS) != OK: return ""
	var path: String = TRACKS.path_join("clip_%s_%s.res" % [Time.get_ticks_usec(),randi()])
	return path if ResourceSaver.save(frames,path,ResourceSaver.FLAG_COMPRESS) == OK else ""
