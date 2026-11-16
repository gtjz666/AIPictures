@tool
extends EditorPlugin
const Model: GDScript = preload("res://addons/ali_assets/blueprint_model.gd")

func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(1.0).timeout
	var records: Array = JSON.parse_string(FileAccess.get_file_as_string("res://probe-inputs.json"))
	EditorInterface.open_scene_from_path(str(records[-1]["resource"]))
	await get_tree().create_timer(0.5).timeout
	var ali: Node = get_tree().get_first_node_in_group("ali_assets_editor")
	EditorInterface.get_selection().clear()
	EditorInterface.get_selection().add_node(EditorInterface.get_edited_scene_root())
	ali.call("open_blueprint")
	var window: Window = ali.get("blueprint") as Window
	var data: Dictionary = Model.empty_graph("platformer")
	data["nodes"] = [
		Model.make_node("attack_key", "key", 0, 0, {"code": KEY_J}),
		Model.make_node("condition", "branch", 320, 0, {"condition": "grounded", "invert": false}),
		Model.make_node("sequence", "sequence", 650, 0, {}),
		Model.make_node("attack", "action", 950, 0, {"action": "attack"}),
		Model.make_node("animation", "animation", 1270, 0, {"clip": "attack_right"}),
		Model.make_node("sound", "sound", 1570, 0, {"path": "res://sources/tone.wav", "trigger": "frame", "frame": 2, "interval": 0.2, "volume": -6}),
		Model.make_node("allowed", "boolean", 0, 310, {"name": "can_attack", "value": true}),
		Model.make_node("delay", "delay", 950, 310, {"seconds": 0.2}),
		Model.make_node("custom", "custom", 1270, 310, {"script": "res://sources/custom.gd"})]
	data["edges"] = [
		{"from": "attack_key", "from_port": 1, "to": "condition"},
		{"from": "condition", "to": "sequence"},
		{"from": "allowed", "to": "condition", "to_port": 1},
		{"from": "sequence", "to": "attack"},
		{"from": "sequence", "from_port": 1, "to": "delay"},
		{"from": "attack", "to": "animation"},
		{"from": "animation", "to": "sound"},
		{"from": "delay", "to": "custom"}]
	for node: Dictionary in data["nodes"]:
		node["position"][0] += 60
		node["position"][1] += 100
	window.call("change", "展示蓝图", data)
	window.size = Vector2i(1600, 900)
	var graph: GraphEdit = window.get("graph") as GraphEdit
	graph.zoom = 0.75
	graph.scroll_offset = Vector2(-40, -40)
	await get_tree().create_timer(1.0).timeout
	RenderingServer.force_draw()
	var image: Image = window.get_texture().get_image()
	assert(image != null and image.save_png("res://graph-window.png") == OK)
	print("ALI_GRAPH_VISUAL_OK")
	window.hide()
	get_tree().quit.call_deferred(0)
