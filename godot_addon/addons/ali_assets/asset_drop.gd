@tool
extends RefCounted
## Bridge between native file drops and the editor's typed resource slots.
const Link: GDScript = preload("resource_link.gd")


static func project_file(raw: String) -> String:
	var path: String = raw.replace("\\", "/")
	if not path.begins_with("res://"):
		var root: String = ProjectSettings.globalize_path("res://").replace("\\", "/").trim_suffix("/") + "/"
		path = path.simplify_path()
		var prefix: bool = path.to_lower().begins_with(root.to_lower()) if OS.get_name() == "Windows" else path.begins_with(root)
		if not prefix:
			return ""
		path = "res://" + path.substr(root.length())
	return path if Link.project_path(path) else ""


static func from_drag(payload: Variant) -> String:
	if not payload is Dictionary:
		return ""
	if payload.get("type") == "files" and payload.get("files", []).size() == 1:
		return project_file(str(payload["files"][0]))
	if payload.get("type") == "resource" and payload.get("resource") is Resource:
		return project_file(payload["resource"].resource_path)
	return ""


static func for_slot(path: String, filter: String) -> String:
	if path.is_empty() or filter not in ["image", "audio"] or not path.begins_with("res://generated/ali_assets/") or path.get_file() != "asset.tscn":
		return path
	var receipt: String = path.get_base_dir().path_join("asset.json")
	if not FileAccess.file_exists(receipt):
		return path
	var record: Variant = JSON.parse_string(FileAccess.get_file_as_string(receipt))
	if not record is Dictionary or record.get("scene") != path or record.get("preset") != filter:
		return path
	var files: Variant = record.get("files")
	if not files is Array or files.size() != 1 or not files[0] is Dictionary:
		return path
	var name: String = str(files[0].get("output", ""))
	if name.is_empty() or name != name.get_file() or name.contains("\\") or name.contains(".."):
		return path
	return path.get_base_dir().path_join(name)


static func contains(control: Control, screen_point: Vector2) -> bool:
	if not control.is_visible_in_tree():
		return false
	var item: Node = control
	while item is Control:
		var parent: Control = item as Control
		if parent == control or parent.clip_contents:
			var local: Vector2 = parent.get_screen_transform().affine_inverse() * screen_point
			if not Rect2(Vector2.ZERO, parent.size).has_point(local):
				return false
		item = parent.get_parent()
	return true


static func node_at(graph: GraphEdit, screen_point: Vector2) -> String:
	if not contains(graph, screen_point):
		return ""
	var nodes: Array[Node] = graph.get_children()
	nodes.reverse()
	for node: Node in nodes:
		if node is GraphNode and contains(node as Control, screen_point):
			return str(node.name)
	return ""


static func import_files(requester: Node) -> bool:
	var filesystem: EditorFileSystem = EditorInterface.get_resource_filesystem()
	var tree: SceneTree = requester.get_tree()
	var deadline: int = Time.get_ticks_msec() + 30000
	while filesystem.is_scanning() and Time.get_ticks_msec() < deadline:
		await tree.process_frame
	if not is_instance_valid(requester) or not requester.is_inside_tree() or filesystem.is_scanning():
		return false
	filesystem.scan()
	await tree.process_frame
	while filesystem.is_scanning() and Time.get_ticks_msec() < deadline:
		await tree.process_frame
	return is_instance_valid(requester) and requester.is_inside_tree() and not filesystem.is_scanning()


static func clips(frames: SpriteFrames) -> PackedStringArray:
	var result: PackedStringArray = []
	if frames != null:
		for name: String in frames.get_animation_names():
			if frames.get_frame_count(name) > 0 and frames.get_animation_speed(name) > 0:
				result.append(name)
	return result


static func copy_clip(target: SpriteFrames, name: String, source: SpriteFrames, clip: String, still: bool = false) -> void:
	if target.has_animation(name):
		target.clear(name)
	else:
		target.add_animation(name)
	target.set_animation_speed(name, source.get_animation_speed(clip))
	target.set_animation_loop(name, not still and source.get_animation_loop(clip))
	for index: int in range(1 if still else source.get_frame_count(clip)):
		target.add_frame(name, source.get_frame_texture(clip, index), source.get_frame_duration(clip, index))
