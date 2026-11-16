@tool
extends EditorPlugin

func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(0.5).timeout
	var rows: Array = JSON.parse_string(FileAccess.get_file_as_string("res://probe-inputs.json"))
	var target: String = str(rows[-1]["resource"])
	EditorInterface.open_scene_from_path(target)
	await get_tree().create_timer(0.5).timeout
	var character: Node = EditorInterface.get_edited_scene_root()
	assert(character is CharacterBody2D)
	EditorInterface.get_selection().clear()
	EditorInterface.get_selection().add_node(character)
	var ali: Node = get_tree().get_first_node_in_group("ali_assets_editor")
	assert(ali != null)
	ali.call("open_blueprint")
	var dialog: AcceptDialog = ali.get("blueprint") as AcceptDialog
	assert(dialog.visible)
	ali.set("binding_property", "key_attack")
	ali.set("binding_button", dialog.get_ok_button())
	var original_key: int = int(character.get("key_attack"))
	var new_key: Key = KEY_K if original_key != KEY_K else KEY_L
	var event: InputEventKey = InputEventKey.new()
	event.pressed = true
	event.physical_keycode = new_key
	ali.call("_input", event)
	assert(int(character.get("key_attack")) == new_key)
	var manager: EditorUndoRedoManager = ali.call("get_undo_redo")
	var history: UndoRedo = manager.get_history_undo_redo(manager.get_object_history_id(character))
	history.undo()
	history.undo()
	assert(int(character.get("key_attack")) == original_key)
	history.redo()
	history.redo()
	assert(int(character.get("key_attack")) == new_key)
	var saved: PackedScene = PackedScene.new()
	assert(saved.pack(character) == OK)
	assert(ResourceSaver.save(saved, target) == OK)
	var fresh: PackedScene = ResourceLoader.load(target, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var copy: Node = fresh.instantiate()
	assert(int(copy.get("key_attack")) == new_key)
	copy.free()
	dialog.hide()
	var file: FileAccess = FileAccess.open("res://blueprint-proof.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"key_rebound": true, "undo_redo": true, "scene_persisted": true, "actual_editor": true}))
	file.close()
	print("ALI_EDITOR_BLUEPRINT_OK")
	get_tree().quit.call_deferred(0)
