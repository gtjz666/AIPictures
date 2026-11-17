@tool
extends EditorPlugin
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Role: GDScript = preload("res://addons/ali_assets/blueprint_model.gd")
const Slot: GDScript = preload("res://addons/ali_assets/resource_slot.gd")
const Preview: GDScript = preload("res://addons/ali_assets/resource_preview.gd")


func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(0.6).timeout
	var ali: Node = get_tree().get_first_node_in_group("ali_assets_editor")
	ali.call("open_game_window")
	var window: Window = ali.get("game_window") as Window
	var graph: Dictionary = Model.scene_preset()
	graph["nodes"].append(Model.module("button_test", "button", 600, 0))
	assert(window.call("change", "按钮测试", graph))
	window.set("selected_id", "button_test")
	window.call("show_inspector")
	var inspector: VBoxContainer = window.get("inspector") as VBoxContainer
	var slots: Array[Node] = inspector.find_children("*", "VBoxContainer", true, false).filter(func(node: Node) -> bool: return node.get_script() == Slot)
	assert(slots.size() == 6)
	var image: VBoxContainer = slots[0] as VBoxContainer
	var files: Dictionary = {"type":"files","files":PackedStringArray(["res://fixtures/button.png"])}
	assert(image.call("_can_drop_data", Vector2.ZERO, files))
	assert(not image.call("_can_drop_data", Vector2.ZERO, {"type":"files","files":PackedStringArray(["res://fixtures/tone.wav"])}))
	assert(image.call("_can_drop_data", Vector2.ZERO, {"type":"resource","resource":load("res://fixtures/button.png")}))
	image.call("_drop_data", Vector2.ZERO, files)
	assert(Model.find(window.get("data"), "button_test")["params"]["normal_texture"] == files["files"][0])
	assert(not Model.find(window.get("data"), "button_test")["resources"]["normal_texture"]["uid"].is_empty())
	var history: UndoRedo = window.get("history") as UndoRedo
	history.undo()
	assert(Model.find(window.get("data"), "button_test")["params"]["normal_texture"].is_empty())
	history.redo()
	window.set("operation", "save")
	window.call("file_selected", "res://button_graph.json")
	window.call("parameter", "normal_texture", "")
	window.set("operation", "load")
	window.call("file_selected", "res://button_graph.json")
	assert(Model.find(window.get("data"), "button_test")["params"]["normal_texture"] == files["files"][0])
	var legacy: Node = Node.new()
	var legacy_script: GDScript = GDScript.new()
	legacy_script.source_code = "extends Node\nconst API_VERSION: int = 4\n@export var compiled_blueprint: Dictionary = {}\n"
	assert(legacy_script.reload() == OK)
	legacy.set_script(legacy_script)
	window.set("target", legacy)
	window.call("apply_game")
	assert((window.get("message") as Label).text.contains("旧运行模块"))
	legacy.free()
	window.set("target", null)
	# Collapsing and rebuilding preserves the editor-project preference.
	var sections: Array[Node] = inspector.find_children("*", "Button", true, false).filter(func(node: Node) -> bool: return (node as Button).toggle_mode)
	assert(sections.size() >= 4)
	var fold: Button = sections[0] as Button
	fold.button_pressed = false
	window.call("show_inspector")
	sections = inspector.find_children("*", "Button", true, false).filter(func(node: Node) -> bool: return (node as Button).toggle_mode)
	assert(not (sections[0] as Button).button_pressed)
	(sections[0] as Button).button_pressed = true
	slots = inspector.find_children("*", "VBoxContainer", true, false).filter(func(node: Node) -> bool: return node.get_script() == Slot)
	image = slots[0] as VBoxContainer
	var changed: Image = Image.create(96, 48, false, Image.FORMAT_RGBA8)
	changed.fill(Color.MAGENTA)
	assert(changed.save_png("res://fixtures/button.png") == OK)
	var filesystem: EditorFileSystem = EditorInterface.get_resource_filesystem()
	while filesystem.is_scanning():
		await get_tree().process_frame
	filesystem.update_file("res://fixtures/button.png")
	filesystem.reimport_files(PackedStringArray(["res://fixtures/button.png"]))
	await get_tree().create_timer(0.2).timeout
	var observed: Color = (image.get("icon") as TextureRect).texture.get_image().get_pixel(0, 0)
	assert(observed.is_equal_approx(Color.MAGENTA), "Reimported pixel: " + str(observed))
	var original: Animation = load("res://fixtures/movement.tres") as Animation
	var before: String = FileAccess.get_sha256("res://fixtures/movement.tres")
	var preview: Window = Preview.new()
	add_child(preview)
	preview.call("present", original)
	preview.call("play")
	await get_tree().create_timer(0.2).timeout
	assert(is_instance_valid(preview.get("ghost")))
	assert((preview.get("ghost") as Control).position.x > 20)
	var player: AnimationPlayer = preview.get("player") as AnimationPlayer
	assert(not player.get_animation("preview").track_is_enabled(1))
	preview.call("pause")
	assert(not player.is_playing())
	preview.call("stop")
	assert((preview.get("ghost") as Control).position == Vector2(260, 140))
	preview.call("finish")
	assert(FileAccess.get_sha256("res://fixtures/movement.tres") == before and original.track_is_enabled(1))
	var sound_preview: Window = Preview.new()
	add_child(sound_preview)
	sound_preview.call("present", load("res://fixtures/tone.wav"))
	sound_preview.call("play")
	assert((sound_preview.get("sound") as AudioStreamPlayer).playing)
	sound_preview.call("pause")
	assert((sound_preview.get("sound") as AudioStreamPlayer).stream_paused)
	sound_preview.call("finish")
	var frames_preview: Window = Preview.new()
	add_child(frames_preview)
	frames_preview.call("present", load("res://fixtures/renamed_frames.tres"))
	frames_preview.call("play")
	assert((frames_preview.get("sprite") as AnimatedSprite2D).is_playing())
	frames_preview.call("finish")
	# Native scene root must remain unchanged by editor preview.
	ali.call("open_blueprint")
	var role_window: Window = ali.get("blueprint") as Window
	var role: Dictionary = Role.preset("two_way")
	role["nodes"].append(Role.make_node("sound_test", "sound", 700, 0, {"path":"", "trigger":"start", "frame":0, "interval":0.25, "volume":-8.0}))
	role_window.call("change", "角色资源槽", role)
	role_window.set("selected_id", "sound_test")
	role_window.call("show_inspector")
	var role_inspector: VBoxContainer = role_window.get("inspector") as VBoxContainer
	var role_slots: Array[Node] = role_inspector.find_children("*", "VBoxContainer", true, false).filter(func(node: Node) -> bool: return node.get_script() == Slot)
	assert(role_slots.size() == 1)
	role_slots[0].call("assign", "res://fixtures/tone.wav")
	assert(Role.find_node(role_window.get("data"), "sound_test")["params"]["path"] == "res://fixtures/tone.wav")
	assert((role_window.get("graph") as GraphEdit).get_node("sound_test").get_child_count() < 4)
	role_window.hide()
	window.hide()
	await get_tree().process_frame
	var file: FileAccess = FileAccess.open("res://blueprint05-editor-proof.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"file_and_resource_drag":true,"wrong_type_rejected":true,"resource_undo_redo":true,"save_json_reload":true,"legacy_runtime_guard":true,"reimport_refresh":true,"fold_state":true,"isolated_animation_play_pause_reset":true,"method_tracks_disabled":true,"source_unchanged":true,"audio_play_pause_close":true,"sprite_frames_play":true,"role_compact_inspector":true}, "\t"))
	file.close()
	get_tree().quit.call_deferred(0)
