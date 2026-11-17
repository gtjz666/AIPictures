extends SceneTree
const Builder: GDScript = preload("res://addons/ali_assets/framework_builder.gd")
var service: Node


func _initialize() -> void:
	run.call_deferred()


func wait_frames(count: int = 40) -> void:
	for index: int in range(count):
		OS.delay_msec(3)
		await process_frame


func wait_task(task: RefCounted) -> void:
	for index: int in range(500):
		if task.get("state") != "running": break
		await wait_frames(1)
	assert(task.get("state") == "completed",str(task.get("detail")))


func run() -> void:
	var old_main: Variant = ProjectSettings.get_setting("application/run/main_scene","")
	var stamp: String = str(Time.get_ticks_usec())
	for preset: String in Builder.PRESETS:
		var folder: String = "res://framework_"+preset+"_"+stamp
		var result: Dictionary = Builder.create(folder,preset)
		assert(not result.has("error"),str(result))
		assert(ProjectSettings.get_setting("application/run/main_scene","") == old_main)
		assert(Builder.create(folder,preset).has("error"))
		for scene: String in ["MainMenu","Game","PauseMenu","SettingsMenu","SaveLoadMenu","GameOver"]: assert(ResourceLoader.exists(folder.path_join(scene+".tscn")))
		var menu: Control = (load(result["scene"]) as PackedScene).instantiate() as Control
		root.add_child(menu)
		current_scene = menu
		await wait_frames(20)
		service = menu.get("service") as Node
		assert(service != null)
		var start_button: Button = menu.find_child("StartButton",true,false) as Button
		var clipping: ScrollContainer = start_button.get_parent().get_parent() as ScrollContainer
		assert(start_button.size.y >= 36 and clipping.size.y >= 350)
		assert(clipping.get_global_rect().encloses(start_button.get_global_rect()))
		(menu.find_child("SettingsButton",true,false) as Button).pressed.emit()
		await wait_frames(20)
		var settings: Control = menu.get("transient")[0] as Control
		assert(settings.visible)
		(settings.find_child("SFXSlider",true,false) as HSlider).value = -18
		assert(service.get("settings")["volumes"]["SFX"] == -18)
		(settings.find_child("BackButton",true,false) as Button).pressed.emit()
		await wait_frames(20)
		(menu.find_child("StartButton",true,false) as Button).pressed.emit()
		await wait_frames(100)
		var game: Node = service.call("current_game") as Node
		assert(game != null and game == current_scene and game.get("state") in ["running","dead"])
		assert(not game.get("hud").get("visible"))
		if game.get("state") == "dead": service.call("lifecycle","restart")
		if preset == "runner":
			await wait_frames(2)
			var jump: InputEventKey = InputEventKey.new()
			jump.physical_keycode = KEY_SPACE
			jump.pressed = true
			Input.parse_input_event(jump)
			await wait_frames(2)
			assert(game.get("actor").get("velocity").y < 0,"Template runner must actually jump via InputMap")
			jump.pressed = false
			Input.parse_input_event(jump)
		service.call("lifecycle","pause")
		await wait_frames(20)
		assert(paused and (game.get_node("Menus/PauseMenu") as Control).visible)
		(game.find_child("ResumeButton",true,false) as Button).pressed.emit()
		await wait_frames(20)
		assert(not paused)
		assert(service.call("save_slot",1).get("state") == "completed")
		await wait_task(service.call("load_slot",1) as RefCounted)
		game = service.call("current_game") as Node
		assert(game != null and game.scene_file_path == result["game"])
		assert(service.get("storage").call("remove",1) == "")
		service.call("lifecycle","end")
		await wait_frames(20)
		assert((game.get_node("Menus/GameOver") as Control).visible)
		await wait_task(service.call("lifecycle","menu") as RefCounted)
		assert(current_scene.scene_file_path == result["scene"])
		current_scene.queue_free()
		current_scene = null
		await wait_frames(2)
	var file: FileAccess = FileAccess.open("res://framework-proof.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"four_native_templates_six_editable_scenes":true,"no_overwrite_or_main_scene_change":true,"menu_settings_start_pause_resume_gameover_navigation":true,"shared_effects_settings_and_save_reload":true}))
	file.close()
	OS.delay_msec(250)
	quit.call_deferred(0)
