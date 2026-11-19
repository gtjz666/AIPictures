@tool
extends RefCounted
const Library: GDScript = preload("game_library.gd")
const Model: GDScript = preload("game_model.gd")
const SceneRuntime: GDScript = preload("game_runtime.gd")
const RUNTIME_NAME: String = "AlIBlueprint"
const RUNTIME_FILES: Array[String] = ["framework_menu.gd", "framework_player.gd", "animation_binding.gd", "subgraph_library.gd", "subgraph_runtime.gd", "game_audio_tools.gd", "framework_input.gd", "framework_storage.gd", "framework_scenes.gd", "framework_services.gd", "game_world_tools.gd", "blueprint_types.gd", "blueprint_task.gd", "blueprint_access.gd", "blueprint_events.gd", "extended_registry.gd", "game_animations.gd", "game_tasks.gd", "game_features.gd", "resource_link.gd", "game_widgets.gd", "game_registry.gd", "game_library.gd", "game_program.gd", "game_runtime.gd", "game_model.gd", "game_assets.gd", "game_actor.gd", "game_world.gd", "game_spawner.gd", "game_audio.gd", "game_hud.gd"]


static func scene_runtime(root: Node) -> Node:
	if not is_instance_valid(root): return null
	if "game_blueprint" in root: return root
	for child: Node in root.get_children():
		if child.get_script() == SceneRuntime: return child
	return null


static func new_runtime() -> Node2D:
	var runtime: Node2D = SceneRuntime.new()
	runtime.name = RUNTIME_NAME
	return runtime


static func create_canvas(path: String) -> String:
	if not path.begins_with("res://") or ".." in path.split("/") or path.get_extension() != "tscn":
		return "请在当前项目内保存新场景。"
	if FileAccess.file_exists(path): return "同名场景已存在，请换一个名称。"
	var root: Node2D = Node2D.new()
	root.name = path.get_file().get_basename().validate_node_name()
	var runtime: Node2D = new_runtime()
	root.add_child(runtime)
	runtime.owner = root
	runtime.set("game_blueprint", Model.empty_scene(path))
	var scene: PackedScene = PackedScene.new()
	var packed: Error = scene.pack(root)
	root.free()
	return "" if packed == OK and ResourceSaver.save(scene, path) == OK else "场景保存失败。"


static func create_scene(data: Dictionary, path: String) -> String:
	var compiled: Dictionary = Library.compile(data)
	var problem: String = str(compiled.get("error", ""))
	if not problem.is_empty():
		return problem
	if not path.begins_with("res://") or ".." in path or path.get_extension() != "tscn":
		return "请在当前项目内创建.tscn场景。"
	if FileAccess.file_exists(path):
		return "场景已存在，请选择新名称；编辑现有游戏请绑定并应用。"
	for name: String in RUNTIME_FILES:
		if not FileAccess.file_exists("res://addons/ali_assets/" + name):
			return "插件运行模块缺失，请重新安装插件：" + name
	var folder: String = path.get_basename() + "_modules_" + str(Time.get_ticks_usec())
	if DirAccess.make_dir_recursive_absolute(folder) != OK:
		return "无法创建模块目录。"
	var source: String = (load("res://addons/ali_assets/game_builder.gd") as GDScript).resource_path.get_base_dir()
	for name: String in RUNTIME_FILES:
		var input: String = source.path_join(name)
		var file: FileAccess = FileAccess.open(folder.path_join(name), FileAccess.WRITE)
		if file == null:
			return "模块写入失败：" + name
		file.store_string(FileAccess.get_file_as_string(input))
		file.close()
	var root: Node2D = Node2D.new()
	root.name = "SceneGame" if data.get("template") == "scene2d" else "RunnerGame"
	root.set_script(load(folder.path_join("game_runtime.gd")))
	root.set("game_blueprint", data.duplicate(true))
	root.set("compiled_blueprint", compiled["data"])
	root.set("compiled_signature", compiled["signature"])
	var scene: PackedScene = PackedScene.new()
	var packed: Error = scene.pack(root)
	root.free()
	if packed != OK or ResourceSaver.save(scene, path) != OK:
		return "场景保存失败。"
	return ""
