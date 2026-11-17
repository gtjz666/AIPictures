@tool
extends VBoxContainer
signal value_changed(path: String)
const Link: GDScript = preload("resource_link.gd")
const Preview: GDScript = preload("resource_preview.gd")
var filter: String = "resource"
var path: String = ""
var identity: Dictionary = {}
var picker: FileDialog
var file_button: Button
var icon: TextureRect
var note: Label
var popup: Window
var watched: Resource


func setup(kind: String, value: String) -> void:
	filter = kind
	path = value
	identity = Link.descriptor(value)
	custom_minimum_size.y = 76
	var row: HBoxContainer = HBoxContainer.new()
	add_child(row)
	icon = TextureRect.new()
	icon.custom_minimum_size = Vector2(56, 56)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(icon)
	file_button = Button.new()
	file_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	file_button.clip_text = true
	file_button.mouse_filter = Control.MOUSE_FILTER_PASS
	file_button.pressed.connect(choose)
	file_button.set_drag_forwarding(Callable(), _can_drop_data, _drop_data)
	row.add_child(file_button)
	var clear: Button = Button.new()
	clear.text = "×"
	clear.tooltip_text = "清空资源"
	clear.pressed.connect(func() -> void: assign(""))
	clear.set_drag_forwarding(Callable(), _can_drop_data, _drop_data)
	row.add_child(clear)
	var preview: Button = Button.new()
	preview.text = "试听／预览"
	preview.pressed.connect(open_preview)
	preview.set_drag_forwarding(Callable(), _can_drop_data, _drop_data)
	add_child(preview)
	note = Label.new()
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(note)
	picker = FileDialog.new()
	picker.access = FileDialog.ACCESS_RESOURCES
	picker.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	picker.force_native = true
	picker.file_selected.connect(assign)
	add_child(picker)
	if Engine.is_editor_hint():
		EditorInterface.get_resource_filesystem().filesystem_changed.connect(refresh_from_filesystem)
		EditorInterface.get_resource_filesystem().resources_reimported.connect(func(files: PackedStringArray) -> void:
			if path in files:
				ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_REPLACE)
				refresh())
	refresh()


func drag_path(data: Variant) -> String:
	if not data is Dictionary:
		return ""
	if data.get("type") == "files" and data.get("files", []).size() == 1:
		return str(data["files"][0])
	if data.get("type") == "resource" and data.get("resource") is Resource:
		return (data["resource"] as Resource).resource_path
	return ""


func _can_drop_data(_at_position: Vector2, data: Variant) -> bool:
	var candidate: String = drag_path(data)
	return not candidate.is_empty() and Link.problem(candidate, filter).is_empty()


func _drop_data(_at_position: Vector2, data: Variant) -> void:
	var candidate: String = drag_path(data)
	if not candidate.is_empty():
		assign(candidate)


func assign(value: String) -> void:
	var error: String = Link.problem(value, filter)
	if not error.is_empty():
		note.text = error
		note.modulate = Color.SALMON
		return
	path = value
	identity = Link.descriptor(path)
	refresh()
	value_changed.emit(path)


func refresh_from_filesystem() -> void:
	if not is_inside_tree():
		return
	var located: String = Link.resolve(identity)
	if not located.is_empty() and located != path:
		assign(located)
	else:
		refresh()


func refresh() -> void:
	if file_button == null:
		return
	file_button.text = "拖入或选择资源…" if path.is_empty() else path.get_file()
	tooltip_text = path
	icon.texture = null
	var error: String = Link.problem(path, filter)
	note.text = error if not error.is_empty() else "拖放替换 · 仅项目资源" if path.is_empty() else path
	note.modulate = Color.SALMON if not error.is_empty() else Color.WHITE
	if path.is_empty() or not error.is_empty() or filter == "module":
		if is_instance_valid(watched) and watched.changed.is_connected(refresh):
			watched.changed.disconnect(refresh)
		watched = null
		return
	var resource: Resource = load(path)
	if resource != watched:
		if is_instance_valid(watched) and watched.changed.is_connected(refresh):
			watched.changed.disconnect(refresh)
		watched = resource
		watched.changed.connect(refresh)
	if resource is Texture2D:
		icon.texture = resource as Texture2D
	elif Link.frames(resource) != null:
		var frames: SpriteFrames = Link.frames(resource)
		for clip: StringName in frames.get_animation_names():
			if frames.get_frame_count(clip) > 0:
				icon.texture = frames.get_frame_texture(clip, 0)
				break


func choose() -> void:
	var types: Dictionary = {"image":"*.png,*.jpg,*.jpeg,*.webp,*.svg,*.tres", "audio":"*.wav,*.ogg,*.mp3,*.tres", "scene":"*.tscn,*.scn", "frames":"*.tres,*.res,*.tscn", "script":"*.gd", "module":"*.json"}
	picker.filters = PackedStringArray([str(types.get(filter, "*.tres,*.res")) + " ; " + filter])
	if filter == "resource":
		picker.filters = PackedStringArray()
	picker.popup_centered(Vector2i(800, 540))


func open_preview() -> void:
	if path.is_empty() or not Link.problem(path, filter).is_empty() or filter == "module":
		return
	if is_instance_valid(popup):
		popup.queue_free()
	popup = Preview.new()
	add_child(popup)
	popup.call("present", load(path))


func _exit_tree() -> void:
	if is_instance_valid(watched) and watched.changed.is_connected(refresh):
		watched.changed.disconnect(refresh)
