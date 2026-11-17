@tool
extends RefCounted
## Runtime-safe project resource identity. No editor classes or absolute paths.
const TYPES: Dictionary = {"image":"Texture2D", "audio":"AudioStream", "frames":"SpriteFrames", "scene":"PackedScene", "animation":"Animation", "library":"AnimationLibrary", "tileset":"TileSet", "script":"GDScript", "resource":"Resource"}


static func project_path(path: String) -> bool:
	return path.begins_with("res://") and not ".." in path and not path.contains("\\")


static func descriptor(path: String) -> Dictionary:
	if path.is_empty():
		return {}
	var uid: int = ResourceLoader.get_resource_uid(path) if ResourceLoader.exists(path) else ResourceUID.INVALID_ID
	return {"path": path, "uid": ResourceUID.id_to_text(uid) if uid != ResourceUID.INVALID_ID else ""}


static func resolve(row: Dictionary) -> String:
	var path: String = str(row.get("path", ""))
	if not project_path(path):
		return ""
	var uid: int = ResourceUID.text_to_id(str(row.get("uid", ""))) if str(row.get("uid", "")).begins_with("uid://") else ResourceUID.INVALID_ID
	if uid != ResourceUID.INVALID_ID and ResourceUID.has_id(uid):
		var located: String = ResourceUID.get_id_path(uid)
		if project_path(located) and ResourceLoader.exists(located):
			return located
	if ResourceLoader.exists(path):
		var current: int = ResourceLoader.get_resource_uid(path)
		if uid != ResourceUID.INVALID_ID and current != ResourceUID.INVALID_ID and current != uid:
			return ""
		return path
	return path if FileAccess.file_exists(path) and path.get_extension() == "json" else ""


static func normalize(data: Dictionary) -> Dictionary:
	var result: Dictionary = data.duplicate(true)
	var nodes: Variant = result.get("nodes", [])
	if not nodes is Array:
		return result
	for raw: Variant in nodes:
		if not raw is Dictionary or not raw.get("params") is Dictionary:
			continue
		var node: Dictionary = raw
		var refs: Variant = node.get("resources", {})
		if not refs is Dictionary:
			continue
		for field: Variant in refs:
			if not field is String or not refs[field] is Dictionary:
				continue
			# A deliberate manual change of path takes precedence over stale metadata.
			if node.get("params", {}).get(field) != refs[field].get("path"):
				continue
			var path: String = resolve(refs[field])
			if not path.is_empty():
				node["params"][field] = path
				node["resources"][field] = descriptor(path)
	return result


static func metadata_problem(node: Dictionary) -> String:
	var refs: Variant = node.get("resources", {})
	if not refs is Dictionary:
		return "资源标识格式无效。"
	for field: Variant in refs:
		if not field is String or not refs[field] is Dictionary:
			return "资源标识格式无效。"
		var row: Dictionary = refs[field]
		if node.get("params", {}).get(field) == row.get("path") and not str(row.get("path", "")).is_empty() and resolve(row).is_empty():
			return "资源丢失或UID已变化，请重新选择：" + str(row.get("path", ""))
	return ""


static func frames(resource: Resource) -> SpriteFrames:
	if resource is SpriteFrames:
		return resource as SpriteFrames
	if resource is PackedScene:
		var state: SceneState = (resource as PackedScene).get_state()
		for index: int in range(state.get_node_count()):
			for prop: int in range(state.get_node_property_count(index)):
				if state.get_node_property_name(index, prop) == &"sprite_frames":
					return state.get_node_property_value(index, prop) as SpriteFrames
	return null


static func problem(path: String, filter: String) -> String:
	if path.is_empty():
		return ""
	if not project_path(path):
		return "请选择当前Godot项目内的资源。"
	if filter == "module":
		return "" if path.get_extension() == "json" and FileAccess.file_exists(path) else "请选择项目内子图JSON。"
	if not ResourceLoader.exists(path):
		return "资源不存在或尚未导入：" + path
	var resource: Resource = load(path)
	if resource == null:
		return "资源无法加载：" + path
	if filter == "frames":
		return "" if frames(resource) != null else "需要SpriteFrames或包含它的角色场景；单张图片不是动画。"
	var expected: String = str(TYPES.get(filter, filter))
	return "" if resource.is_class(expected) else "需要" + expected + "，收到" + resource.get_class() + "。"
