extends SceneTree
const Builder: GDScript = preload("res://addons/ali_assets/framework_builder.gd")


func _initialize() -> void:
	run.call_deferred()


func run() -> void:
	root.size = Vector2i(960,540)
	var result: Dictionary = Builder.create("res://visual_framework","platformer")
	assert(not result.has("error"),str(result))
	var menu: Control = (load(result["scene"]) as PackedScene).instantiate() as Control
	root.add_child(menu)
	current_scene = menu
	await create_timer(0.5).timeout
	RenderingServer.force_draw()
	assert(root.get_texture().get_image().save_png("res://blueprint-2d-menu.png") == OK)
	menu.call("perform","settings")
	await create_timer(0.4).timeout
	RenderingServer.force_draw()
	assert(root.get_texture().get_image().save_png("res://blueprint-2d-settings.png") == OK)
	menu.queue_free()
	current_scene = null
	await process_frame
	OS.delay_msec(250)
	quit(0)
