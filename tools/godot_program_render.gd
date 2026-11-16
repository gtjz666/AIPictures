@tool
extends EditorPlugin
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")


func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(0.7).timeout
	var ali: Node = get_tree().get_first_node_in_group("ali_assets_editor")
	ali.call("open_game_window")
	var window: Window = ali.get("game_window") as Window
	window.size = Vector2i(1600, 950)
	var data: Dictionary = Model.add_combo(Model.scene_preset(), "health")
	var health_id: String = ""
	var positions: Dictionary = {"input": [0, 80], "session": [400, 80], "hud": [800, 80], "mixer": [1200, 1600], "screen": [1500, 1600], "damage": [0, 480], "heal": [0, 780], "cooldown": [400, 480], "hp": [800, 480], "format": [800, 780], "notice": [400, 780]}
	for node: Dictionary in data["nodes"]:
		var suffix: String = str(node["id"]).get_slice("_", 2) if str(node["id"]).begins_with("combo_") else str(node["id"])
		node["position"] = positions[suffix]
		if node["kind"] == "health":
			health_id = str(node["id"])
	window.set("selected_id", health_id)
	window.call("assign", data)
	window.call("show_inspector")
	var graph: GraphEdit = window.get("graph") as GraphEdit
	graph.zoom = 0.72
	await get_tree().create_timer(0.4).timeout
	graph.scroll_offset = Vector2(-40, -20)
	await get_tree().create_timer(0.3).timeout
	RenderingServer.force_draw()
	assert(window.get_texture().get_image().save_png("res://blueprint-programming.png") == OK)
	window.hide()
	print("ALI_PROGRAM_RENDER_OK")
	get_tree().quit.call_deferred(0)
