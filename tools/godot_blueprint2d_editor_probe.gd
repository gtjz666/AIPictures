@tool
extends EditorPlugin
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Tools: GDScript = preload("res://addons/ali_assets/game_editor_tools.gd")
const Importer: GDScript = preload("res://addons/ali_assets/asset_import.gd")
const ImportWizard: GDScript = preload("res://addons/ali_assets/asset_import_wizard.gd")
const Preview: GDScript = preload("res://addons/ali_assets/animation_preview.gd")
const Slot: GDScript = preload("res://addons/ali_assets/node_slot.gd")
const Library: GDScript = preload("res://addons/ali_assets/game_library.gd")
const Drop: GDScript = preload("res://addons/ali_assets/asset_drop.gd")


func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(0.3).timeout
	var ali: Node = get_tree().get_first_node_in_group("ali_assets_editor")
	assert(ali != null)
	if FileAccess.file_exists("res://editor2d-proof.json"):
		var reopened: Window = ali.get("game_window") as Window
		assert(reopened != null and reopened.visible)
		var root: Node = EditorInterface.get_edited_scene_root()
		assert(root != null and root.scene_file_path == "res://SceneOne.tscn" and reopened.get("target") == root)
		assert(Model.find(reopened.get("data"),"movement")["params"]["mode"] == "frames")
		var proof: FileAccess = FileAccess.open("res://canvas-autoload-proof.json",FileAccess.WRITE)
		proof.store_string("{\"saved_graph_opened_automatically\":true}")
		proof.close()
		get_tree().quit.call_deferred()
		return
	var dock: Control = ali.get("dock")
	for button: Node in dock.find_children("*","BaseButton",false,false):
		assert(not "模板" in button.get("text"))
	ali.call("open_game_window")
	var window: Window = ali.get("game_window") as Window
	var menu: PopupMenu = window.get("tools_menu").get_popup()
	for index: int in range(menu.item_count):
		assert(not "模板" in menu.get_item_text(index))
	await test_scene_canvas(ali,window)
	window.call("assign",Model.preset())
	await test_direct_drop(window)
	for kind: String in Model.TITLES:
		if kind in Model.SINGLETONS: continue
		window.call("add_module",kind)
		assert(Model.validate(window.get("data")).is_empty())
		window.get("history").call("undo")
	var graph: Dictionary = Model.scene_preset()
	Model.by_kind(graph,"session")["params"]["save_key"] = "editor_"+str(Time.get_ticks_usec())
	var blackboard: Dictionary = Model.module("counter","blackboard",600,100)
	blackboard["params"].merge({"name":"counter","value_type":"vector2","json":"[1,2]"},true)
	graph["nodes"].append(blackboard)
	var write: Dictionary = Model.module("write","set_variable",900,100)
	write["params"].merge({"name":"counter","value_type":"vector2","json":"[3,4]"},true)
	graph["nodes"].append(write)
	var selection: Array[String] = ["counter","write"]
	var clipboard: Dictionary = Tools.copy(graph,selection)
	var pasted: Dictionary = Tools.paste(graph,clipboard)
	assert(not pasted.has("error"),str(pasted))
	assert(pasted["data"]["nodes"][-1]["params"]["name"] == pasted["data"]["nodes"][-2]["params"]["name"])
	assert(pasted["data"]["nodes"][-1]["params"]["name"] != "counter")
	window.call("assign",graph)
	window.set("selected_id","counter")
	window.call("parameter","value_type","color")
	assert(Model.find(window.get("data"),"counter")["params"]["value_type"] == "color")
	window.get("history").call("undo")
	window.call("change","proof paste",pasted["data"])
	var count: int = window.get("data")["nodes"].size()
	window.get("history").call("undo")
	assert(window.get("data")["nodes"].size() == count-2)
	window.get("history").call("redo")
	assert(window.get("data")["nodes"].size() == count)
	window.set("favorites",["animation"])
	window.set("favorites_only",true)
	window.call("filter_palette")
	assert(window.get("results").get("item_count") == 1)
	window.set("favorites_only",false)
	var world: Node2D = Node2D.new()
	world.name = "Source"
	add_child(world)
	var box: VBoxContainer = VBoxContainer.new()
	box.name = "Box"
	world.add_child(box)
	var button: Button = Button.new()
	button.name = "Button"
	button.text = "Original"
	box.add_child(button)
	var slot: HBoxContainer = Slot.new()
	add_child(slot)
	slot.call("setup",world,"")
	assert(slot.call("accepts",button) and not slot.call("accepts",ali))
	slot.call("choose",button)
	assert(slot.get("edit").get("text") == "Box/Button")
	var initial: Vector2 = button.scale
	var node: Dictionary = Model.module("motion","animation",0,0)
	node["params"].merge({"target":"Box/Button","seconds":0.05,"factor":1.2},true)
	var preview: Window = Preview.new()
	add_child(preview)
	preview.call("present",world,node)
	preview.call("play")
	await get_tree().create_timer(0.2).timeout
	assert(preview.get("task").get("state") == "completed",str(preview.get("task").get("detail")))
	assert(button.scale == initial and button.get_parent() == box and button.text == "Original")
	preview.call("stop")
	preview.queue_free()
	var camera: Camera2D = Camera2D.new()
	camera.name = "Camera"
	world.add_child(camera)
	node = Model.module("camera","camera2d",0,0)
	node["params"].merge({"target":"Camera","operation":"zoom","x":1.5,"y":1.5,"seconds":0.05},true)
	preview = Preview.new()
	add_child(preview)
	preview.call("present",world,node)
	preview.call("play")
	await get_tree().create_timer(0.2).timeout
	assert(preview.get("task").get("state") == "completed")
	assert(camera.zoom == Vector2.ONE)
	preview.queue_free()
	slot.queue_free()
	world.queue_free()
	var options: Dictionary = {"sheet":true,"cell":Vector2i(8,8),"margin":Vector2i.ZERO,"gap":Vector2i.ZERO,"fps":12,"clip":"walk","selection":[0,1],"loop":true}
	var result: Dictionary = Importer.frames(["res://fixtures/button.png"],options)
	assert(not result.has("error") and result["count"] == 2,str(result))
	assert(Importer.save(result["resource"],"res://import_frames.tres") == "")
	assert(not Importer.save(result["resource"],"res://import_frames.tres").is_empty())
	var animation: Animation = Importer.animation(result["resource"],"walk")
	assert(animation.track_get_path(0) == NodePath("Visual:texture") and animation.track_get_key_count(0) == 2)
	result = Importer.tileset("res://fixtures/button.png",options)
	assert(not result.has("error") and result["count"] == 2,str(result))
	assert(Importer.save(result["resource"],"res://import_tiles.tres") == "")
	assert(Importer.ordered(["res://10.png","res://2.png"])[0] == "res://2.png")
	var wizard: Window = ImportWizard.new()
	add_child(wizard)
	wizard.call("select_files",PackedStringArray(["res://fixtures/button.png"]))
	wizard.get("import_mode").set("selected",1)
	wizard.call("refresh")
	assert(wizard.get("grid").get("item_count") > 0)
	wizard.queue_free()
	var path: String = "user://ali_blueprint_"+str(Model.by_kind(window.get("data"),"session")["params"]["save_key"])+".json"
	var file: FileAccess = FileAccess.open(path,FileAccess.WRITE)
	file.store_string(JSON.stringify({"signature":Library.signature(window.get("data")),"nodes":{"counter":{"state":"failed","detail":"proof"}},"events":[{"source":"counter","detail":"错误：proof","time":1.0}]}))
	file.close()
	window.call("poll_debug")
	assert(not window.get("debug_snapshot").is_empty())
	window.call("focus_node","counter")
	assert(window.get("selected_id") == "counter")
	file = FileAccess.open("res://editor2d-proof.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"direct_asset_binding":true,"all_new_node_inspectors":true,"typed_copy_paste_namespace_undo_redo":true,"favorites_and_typed_ports":true,"node_slot_root_validation":true,"isolated_animation_and_camera_preview_no_source_mutation":true,"native_sheet_frames_animation_tileset_import_no_overwrite":true,"debug_signature_and_error_source_location":true}))
	file.close()
	window.hide()


func test_direct_drop(window: Window) -> void:
	var paths: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://fixtures/drop.json"))
	assert(Drop.project_file("C:/outside/asset.tscn").is_empty())
	assert(await Drop.import_files(self))
	var walk: String = Drop.project_file(paths["walk"])
	assert(walk.begins_with("res://generated/ali_assets/"))
	assert(ResourceLoader.exists(Drop.for_slot(Drop.project_file(paths["image"]), "image"), "Texture2D"))
	assert(ResourceLoader.exists(Drop.for_slot(Drop.project_file(paths["voice"]), "audio"), "AudioStream"))
	var graph_data: Dictionary = window.get("data")
	var runner: String = str(Model.by_kind(graph_data,"runner")["id"])
	window.call("bind_dropped_asset", runner, walk)
	var settings: Dictionary = Model.by_kind(window.get("data"), "runner")["params"]
	var frames: SpriteFrames = Model.frames_at(settings["frames"])
	assert(frames.get_frame_count("walk_right") == 2)
	assert(frames.get_frame_count("jump_right") == 1 and frames.get_frame_count("death_right") == 1)
	assert(Model.validate(window.get("data"),true).is_empty())
	window.call("bind_dropped_asset", runner, Drop.project_file(paths["jump"]))
	var combined: String = str(Model.by_kind(window.get("data"), "runner")["params"]["frames"])
	assert(combined != settings["frames"])
	frames = Model.frames_at(combined)
	assert(frames.get_frame_count("walk_right") == 2 and frames.get_frame_count("jump_right") == 1)
	window.get("history").undo()
	assert(Model.by_kind(window.get("data"),"runner")["params"]["frames"] == settings["frames"])
	var animation: Dictionary = Model.module("drop_animation","animation",130,120)
	graph_data = window.get("data").duplicate(true)
	graph_data["nodes"].append(animation)
	window.call("assign",graph_data)
	window.call("bind_dropped_asset","drop_animation",walk)
	assert(Model.find(window.get("data"),"drop_animation")["params"]["clip"] == "walk")
	var role_scene: PackedScene = load(Drop.project_file(paths["role"]))
	var role: Node = role_scene.instantiate()
	add_child(role)
	var role_window: Window = preload("res://addons/ali_assets/blueprint_window.gd").new()
	add_child(role_window)
	assert(role_window.call("bind_character",role))
	var role_data: Dictionary = role_window.get("data")
	for node: Dictionary in role_data["nodes"]:
		if node["kind"] != "animation":
			continue
		var id: String = str(node["id"])
		role_window.call("bind_dropped_asset",id,walk)
		var drafted: Dictionary = role_window.get("data")
		var clip: String = str(preload("res://addons/ali_assets/blueprint_model.gd").find_node(drafted,id)["params"]["clip"])
		var draft_frames: SpriteFrames = role_window.get("frames")
		assert(clip.begins_with("walk_ali_") and draft_frames.get_frame_count(clip) == 2)
		assert(not role.get_node("AnimatedSprite2D").get("sprite_frames").has_animation(clip))
		role_window.get("history").undo()
		assert(not role_window.get("frames").has_animation(clip))
		break
	role_window.queue_free()
	role.queue_free()


func test_scene_canvas(ali: Node, window: Window) -> void:
	var Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
	var TrackIO: GDScript = preload("res://addons/ali_assets/frame_track_io.gd")
	var inputs: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://fixtures/drop.json"))
	window.hide()
	window.set("operation","new_canvas")
	window.call("file_selected","res://SceneOne.tscn")
	await get_tree().create_timer(0.3).timeout
	var root: Node = EditorInterface.get_edited_scene_root()
	assert(root != null and root.scene_file_path == "res://SceneOne.tscn")
	assert(window.visible and window.get("target") == root)
	var runtime: Node = Builder.scene_runtime(root)
	assert(runtime != null and runtime.get("game_blueprint")["nodes"].is_empty())
	assert(window.get("data")["nodes"].is_empty() and window.get("data")["edges"].is_empty())
	await test_canvas_layout(window)
	var actor: Node2D = Node2D.new()
	actor.name = "Object"
	root.add_child(actor)
	actor.owner = root
	EditorInterface.get_selection().clear()
	EditorInterface.get_selection().add_node(actor)
	var data: Dictionary = window.get("data").duplicate(true)
	var event: Dictionary = Model.module("on_ready","game_event",60,80)
	var animation: Dictionary = Model.module("movement","animation",450,80)
	animation["params"]["target"] = "Object"
	data["nodes"].append_array([event,animation])
	data["edges"].append({"from":"on_ready","from_port":0,"to":"movement","to_port":0})
	window.call("assign",data)
	var generic: Dictionary = TrackIO.read(PackedStringArray([inputs["frames"]]))
	assert(not generic.has("error"),str(generic.get("error","")))
	assert(generic["frames"].get_frame_texture(generic["clip"],0).get_image().get_pixel(0,0).r > 0.5)
	var png_sequence: Dictionary = TrackIO.read(PackedStringArray([inputs["png_sequence"]]))
	assert(not png_sequence.has("error"),str(png_sequence.get("error","")))
	var numbered_frames: SpriteFrames = png_sequence["frames"]
	var numbered_clip: String = png_sequence["clip"]
	assert(numbered_frames.get_frame_count(numbered_clip) == 2)
	assert(numbered_frames.get_animation_speed(numbered_clip) == 9 and not numbered_frames.get_animation_loop(numbered_clip))
	assert(numbered_frames.get_frame_texture(numbered_clip,0).get_image().get_pixel(0,0).a < 0.6)
	assert(numbered_frames.get_frame_texture(numbered_clip,1).get_image().get_pixel(0,0).g > 0.6)
	window.call("import_track","movement",PackedStringArray([inputs["sheet"]]))
	var track: VBoxContainer = window.get("frame_track")
	assert(track.visible and track.get("fps").value == 8)
	track.call("move_frame",1)
	track.get("fps").value = 10
	track.get("hold").value = 2
	track.get("loop").button_pressed = true
	track.call("save_clip")
	var animation_params: Dictionary = Model.find(window.get("data"),"movement")["params"]
	assert(animation_params["target"] == "Object/AlIVisual")
	assert(animation_params["loops"] == 0 and not animation_params["wait"])
	var resource: SpriteFrames = load(animation_params["frames"])
	var clip: String = animation_params["clip"]
	assert(resource.get_animation_speed(clip) == 10 and resource.get_frame_duration(clip,1) == 2)
	assert(resource.get_frame_texture(clip,0).get_image().get_pixel(0,0).g > 0.6)
	assert(resource.get_frame_texture(clip,1).get_image().get_pixel(0,0).a < 0.6)
	window.call("apply_game")
	assert(actor.has_node("AlIVisual"))
	assert(actor.get_node("AlIVisual").get("sprite_frames").has_animation(clip))
	var manager: EditorUndoRedoManager = ali.call("get_undo_redo")
	var state: UndoRedo = manager.get_history_undo_redo(manager.get_object_history_id(root))
	state.undo()
	assert(not actor.has_node("AlIVisual"))
	state.redo()
	assert(actor.has_node("AlIVisual"))
	var saved_scene: PackedScene = PackedScene.new()
	assert(saved_scene.pack(root) == OK and ResourceSaver.save(saved_scene,root.scene_file_path) == OK)
	# Publish functions through the same editor save route available to users.
	window.call("open_function")
	var function_window: Window = null
	for child: Node in window.get_children():
		if child is Window and "function_mode" in child and child.get("function_mode"): function_window = child
	assert(function_window != null and function_window.get("data")["nodes"].size() == 2)
	function_window.call("connect_modules",&"function_start",0,&"function_return",0)
	var local: String = window.call("function_folder",false)
	assert(DirAccess.make_dir_recursive_absolute(local) == OK)
	assert(DirAccess.make_dir_recursive_absolute(Library.GLOBAL_FUNCTIONS) == OK)
	function_window.call("save_function",false)
	function_window.call("file_selected",local.path_join("LocalWalk.json"))
	function_window.call("save_function",true)
	function_window.call("file_selected",Library.GLOBAL_FUNCTIONS.path_join("GlobalWalk.json"))
	function_window.queue_free()
	var search: LineEdit = window.get("search")
	search.text = "Walk"
	window.call("filter_palette")
	assert(window.get("results").item_count == 2)
	window.set("operation","new_canvas")
	window.call("file_selected","res://SceneTwo.tscn")
	await get_tree().create_timer(0.3).timeout
	assert(window.get("data")["nodes"].is_empty())
	window.call("filter_palette")
	assert(window.get("results").item_count == 1)
	assert("GlobalWalk" in window.get("results").get_item_text(0))
	var outside: Dictionary = window.get("data").duplicate(true)
	var call_module: Dictionary = Model.module("call_module","subgraph",0,0)
	call_module["params"]["path"] = local.path_join("LocalWalk.json")
	outside["nodes"].append(call_module)
	assert("作用域" in Library.compile(outside).get("error",""))
	call_module["params"]["path"] = Library.GLOBAL_FUNCTIONS.path_join("GlobalWalk.json")
	assert(not Library.compile(outside).has("error"))
	search.text = ""
	await test_scene_switching(window)
	window.call("bind_scene",null)


func test_canvas_layout(window: Window) -> void:
	var graph: GraphEdit = window.get("graph")
	var original_size: Vector2i = window.size
	for viewport_size: Vector2i in [Vector2i(1100,700),Vector2i(1580,930)]:
		window.size = viewport_size
		await get_tree().process_frame
		await get_tree().process_frame
		var rect: Rect2 = graph.get_global_rect()
		assert(absf(rect.end.x - (window.size.x - 10)) <= 1.0, str(rect))
		assert(absf(rect.end.y - (window.size.y - 10)) <= 1.0, str(rect))
	var sidebar: PanelContainer = window.get("sidebar")
	var palette: VBoxContainer = window.get("palette")
	var search: LineEdit = window.get("search")
	var inspector_scroll: ScrollContainer = window.get("inspector_scroll")
	var results: ItemList = window.get("results")
	assert(not sidebar.visible and not inspector_scroll.visible)
	window.call("open_palette")
	await get_tree().process_frame
	await get_tree().process_frame
	assert(palette.is_visible_in_tree() and palette.get_window() == window and search.has_focus())
	assert(sidebar.get_global_rect().position.x >= graph.get_global_rect().end.x)
	assert(not inspector_scroll.visible and graph.size.x < window.size.x - 20)
	search.text = "数字常量"
	window.call("filter_palette")
	assert(results.item_count == 1 and results.get_item_metadata(0) == "number")
	search.text_submitted.emit(search.text)
	await get_tree().process_frame
	assert(not palette.visible and inspector_scroll.is_visible_in_tree())
	var module_id: String = window.get("selected_id")
	var widget: GraphNode = graph.get_node(NodePath(module_id))
	assert(widget.selected and Model.find(window.get("data"),module_id)["kind"] == "number")
	window.call("open_palette", module_id, 0, Vector2(310,160))
	assert(palette.visible and not inspector_scroll.visible)
	var esc: InputEventKey = InputEventKey.new()
	esc.keycode = KEY_ESCAPE
	esc.pressed = true
	window.call("on_input", esc)
	assert(not palette.visible and inspector_scroll.visible)
	widget.selected = false
	graph.node_deselected.emit(widget)
	await get_tree().process_frame
	await get_tree().process_frame
	assert(not sidebar.visible and is_equal_approx(graph.size.x, window.size.x - 20.0))
	window.get("history").call("undo")
	assert(window.get("data")["nodes"].is_empty())
	window.size = original_size


func test_scene_switching(window: Window) -> void:
	var scene_menu: MenuButton = window.get("scene_menu")
	var popup: PopupMenu = scene_menu.get_popup()
	window.call("add_module", "number")
	var draft_id: String = window.get("selected_id")
	assert("SceneTwo" in scene_menu.text)
	scene_menu.show_popup()
	await get_tree().process_frame
	assert(popup.visible)
	var first: int = -1
	var second: int = -1
	for index: int in range(popup.item_count):
		match popup.get_item_metadata(index):
			"res://SceneOne.tscn": first = index
			"res://SceneTwo.tscn": second = index
	assert(first >= 0 and second >= 0 and popup.is_item_checked(second))
	popup.hide()
	popup.index_pressed.emit(first)
	await get_tree().create_timer(0.3).timeout
	assert(EditorInterface.get_edited_scene_root().scene_file_path == "res://SceneOne.tscn")
	assert("SceneOne" in scene_menu.text and not Model.find(window.get("data"),"movement").is_empty())
	assert(Model.find(window.get("data"),draft_id).is_empty())
	popup.index_pressed.emit(second)
	await get_tree().create_timer(0.3).timeout
	assert("SceneTwo" in scene_menu.text and Model.find(window.get("data"),draft_id)["kind"] == "number")
	assert(Model.find(window.get("data"),"movement").is_empty())
	scene_menu.show_popup()
	await get_tree().process_frame
	var open_item: int = popup.item_count - 1
	assert(popup.get_item_text(open_item) == "打开其他场景…")
	popup.hide()
	popup.index_pressed.emit(open_item)
	var picker: FileDialog = window.get("chooser")
	assert(window.get("operation") == "open_scene" and picker.file_mode == FileDialog.FILE_MODE_OPEN_FILE)
	var Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
	var other: String = "res://SceneThree.tscn"
	assert(Builder.create_canvas(other).is_empty() and other not in EditorInterface.get_open_scenes())
	picker.hide()
	picker.file_selected.emit(other)
	await get_tree().create_timer(0.3).timeout
	assert(EditorInterface.get_edited_scene_root().scene_file_path == other)
	assert("SceneThree" in scene_menu.text and window.get("data")["nodes"].is_empty())
