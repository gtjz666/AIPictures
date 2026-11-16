@tool
extends EditorPlugin


func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(0.7).timeout
	var ali: Node = get_tree().get_first_node_in_group("ali_assets_editor")
	ali.call("open_game_window")
	var window: Window = ali.get("game_window") as Window
	window.size = Vector2i(1600, 950)
	window.set("selected_id", "runner")
	window.call("show_inspector")
	var graph: GraphEdit = window.get("graph") as GraphEdit
	graph.zoom = 0.55
	await get_tree().create_timer(0.5).timeout
	RenderingServer.force_draw()
	assert(window.get_texture().get_image().save_png("res://game-blueprint.png") == OK)
	window.hide()
	print("ALI_GAME_WINDOW_RENDER_OK")
	get_tree().quit.call_deferred(0)
