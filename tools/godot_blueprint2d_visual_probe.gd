@tool
extends EditorPlugin
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const WindowScript: GDScript = preload("res://addons/ali_assets/game_window.gd")
const Builder: GDScript = preload("res://addons/ali_assets/framework_builder.gd")


func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(0.5).timeout
	var window: Window = WindowScript.new()
	window.force_native = false
	add_child(window)
	var graph: Dictionary = Model.scene_preset()
	graph["edges"] = []
	for index: int in range(graph["nodes"].size()): graph["nodes"][index]["position"] = [1800,index*300]
	for row: Array in [["press","button",20,20],["serial","task_group",330,20],["motion","animation",650,20],["fade","animation",650,330],["camera","camera2d",980,20],["tiles","tilemap",980,420]]:
		var node: Dictionary = Model.module(row[0],row[1],row[2],row[3])
		node["position"][1] = float(node["position"][1])+90.0
		if row[1] == "button": node["params"].merge({"text":"开始冒险","effects_enabled":true},true)
		if row[0] == "motion": node["params"]["target"] = "Player/Visual"
		if row[0] == "fade": node["params"].merge({"mode":"color","target":"Menu","color":"ffffff00"},true)
		graph["nodes"].append(node)
	graph["edges"].append_array([{"from":"press","from_port":0,"to":"serial","to_port":0},{"from":"serial","from_port":0,"to":"motion","to_port":0},{"from":"serial","from_port":1,"to":"fade","to_port":0},{"from":"serial","from_port":4,"to":"camera","to_port":0}])
	window.call("assign",graph)
	window.set("selected_id","motion")
	window.call("show_inspector")
	window.popup_centered(Vector2i(1520,940))
	window.get("graph").set("zoom",0.7)
	window.get("graph").set("scroll_offset",Vector2(-20,-20))
	await get_tree().create_timer(0.3).timeout
	RenderingServer.force_draw()
	assert(window.get_texture().get_image().save_png("res://blueprint-2d-editor.png") == OK)
	window.hide()
	window.queue_free()
	await get_tree().process_frame
	OS.delay_msec(250)
	get_tree().quit.call_deferred(0)
