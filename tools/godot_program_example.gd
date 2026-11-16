extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")


func _initialize() -> void:
	var data: Dictionary = Model.add_combo(Model.add_combo(Model.scene_preset(), "health"), "fsm")
	Model.by_kind(data, "session")["params"]["save_key"] = "blueprint_basics"
	Model.by_kind(data, "hud")["params"].merge({"title":"BLUEPRINT LAB", "subtitle":"J: DAMAGE / K: HEAL / F: STATE", "start_text":"START TEST"}, true)
	var problem: String = Builder.create_scene(data, "res://blueprint_basics.tscn")
	if not problem.is_empty():
		push_error(problem)
		quit(1)
		return
	ProjectSettings.set_setting("application/run/main_scene", "res://blueprint_basics.tscn")
	ProjectSettings.save()
	print("ALI_PROGRAM_EXAMPLE_OK")
	quit()
