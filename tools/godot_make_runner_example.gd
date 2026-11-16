extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")


func _initialize() -> void:
	var path: String = "res://games/runner_game.tscn"
	var problem: String = Builder.create_scene(Model.preset(), path)
	if not problem.is_empty():
		push_error(problem)
		quit(1)
		return
	ProjectSettings.set_setting("application/run/main_scene", path)
	assert(ProjectSettings.save() == OK)
	print("ALI_RUNNER_EXAMPLE_CREATED")
	quit(0)
