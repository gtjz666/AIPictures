@tool
extends EditorPlugin
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Library: GDScript = preload("res://addons/ali_assets/game_library.gd")


func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(0.5).timeout
	var ali: Node = get_tree().get_first_node_in_group("ali_assets_editor")
	ali.call("open_game_window")
	var window: Window = ali.get("game_window") as Window
	window.call("change", "通用模板", Model.scene_preset())
	var history: UndoRedo = window.get("history") as UndoRedo
	history.undo()
	assert(window.get("data")["nodes"].is_empty())
	history.redo()
	window.call("open_palette")
	var search: LineEdit = window.get("search") as LineEdit
	var results: ItemList = window.get("results") as ItemList
	search.text = "数字常量"
	window.call("filter_palette")
	assert(results.item_count == 1 and results.get_item_metadata(0) == "number")
	window.call("add_palette_item", 0)
	var id: String = window.get("selected_id")
	var graph: GraphEdit = window.get("graph") as GraphEdit
	assert((graph.get_node(id) as GraphNode).get_output_port_type(0) == 7)
	var inspector: VBoxContainer = window.get("inspector") as VBoxContainer
	var spin: SpinBox = inspector.find_children("*", "SpinBox", true, false)[0] as SpinBox
	assert(spin != null)
	spin.value = 3.0
	assert(is_instance_valid(spin) and not spin.is_queued_for_deletion())
	assert(Model.find(window.get("data"), id)["params"]["value"] == 3.0)
	history.undo()
	assert(Model.find(window.get("data"), id)["params"]["value"] == 1.0)
	history.redo()
	graph.connection_to_empty.emit(StringName(id), 0, Vector2(500, 200))
	search.text = "数字运算"
	window.call("filter_palette")
	assert(results.item_count == 1 and results.get_item_metadata(0) == "math")
	window.call("add_palette_item", 0)
	var math_id: String = window.get("selected_id")
	assert(graph.is_node_connected(StringName(id), 0, StringName(math_id), 0))
	history.undo()
	assert(Model.find(window.get("data"), math_id).is_empty())
	history.redo()
	var draft: Dictionary = Model.add_combo(Model.add_combo(Model.scene_preset(), "health"), "fsm")
	assert(window.call("change", "预设组合", draft))
	window.call("check_graph")
	assert((window.get("message") as Label).text.begins_with("编译通过"))
	# Save a selected, connected asynchronous task as a reusable graph.
	var source: Dictionary = Model.module("source", "log", 0, 0)
	var task: Dictionary = Model.module("task", "delay", 0, 300)
	var dest: Dictionary = Model.module("dest", "log", 300, 300)
	draft["nodes"].append_array([source, task, dest])
	draft["edges"].append_array([{"from":"source","from_port":0,"to":"task","to_port":0},{"from":"task","from_port":0,"to":"dest","to_port":0}])
	var selected: Array[String] = ["task"]
	var extracted: Dictionary = Library.extract(draft, selected)
	assert(extracted.has("data"))
	window.set("module_draft", extracted["data"])
	assert(DirAccess.make_dir_recursive_absolute(Library.GLOBAL_FUNCTIONS) == OK)
	window.set("operation", "global_function")
	var function_path: String = Library.GLOBAL_FUNCTIONS.path_join("editor_task.json")
	window.call("file_selected", function_path)
	assert(Library.read_module(function_path).has("data"))
	var builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
	assert(builder.create_scene(window.get("data"),"res://generic_from_editor.tscn").is_empty())
	EditorInterface.open_scene_from_path("res://generic_from_editor.tscn")
	await get_tree().create_timer(0.5).timeout
	var root: Node = EditorInterface.get_edited_scene_root()
	assert(root != null and "compiled_blueprint" in root)
	EditorInterface.get_selection().clear()
	EditorInterface.get_selection().add_node(root)
	window.call("bind_selection")
	window.set("selected_id", "session")
	var previous: String = root.get("compiled_signature")
	window.call("parameter", "points_per_second", 3.0)
	window.call("apply_game")
	assert(root.get("compiled_signature") != previous)
	assert(root.get("compiled_signature") == Library.signature(root.get("game_blueprint")))
	var manager: EditorUndoRedoManager = ali.call("get_undo_redo")
	var scene_history: UndoRedo = manager.get_history_undo_redo(manager.get_object_history_id(root))
	scene_history.undo()
	assert(root.get("compiled_signature") == previous)
	scene_history.redo()
	assert(root.get("compiled_signature") == Library.signature(root.get("game_blueprint")))
	window.hide()
	var file: FileAccess = FileAccess.open("res://program-editor-proof.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"native_search_and_typed_ports": true, "drag_to_empty_auto_connect_undo": true, "numeric_field_keeps_control": true, "generic_template_and_combos": true, "subgraph_export": true, "atomic_source_and_compiled_undo": true}))
	file.close()
	print("ALI_PROGRAM_EDITOR_OK")
	get_tree().quit.call_deferred(0)
