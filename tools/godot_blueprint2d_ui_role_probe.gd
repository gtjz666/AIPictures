extends SceneTree
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Builder: GDScript = preload("res://addons/ali_assets/game_builder.gd")
const Access: GDScript = preload("res://addons/ali_assets/blueprint_access.gd")
const RoleModel: GDScript = preload("res://role_runtime/blueprint_model.gd")
const RoleRuntime: GDScript = preload("res://role_runtime/blueprint_runtime.gd")
const Assets: GDScript = preload("res://addons/ali_assets/game_assets.gd")


func _initialize() -> void:
	run.call_deferred()


func add(graph: Dictionary, id: String, kind: String, p: Dictionary) -> Dictionary:
	var node: Dictionary = Model.module(id,kind,0,0)
	node["params"].merge(p,true)
	graph["nodes"].append(node)
	return node


func edge(graph: Dictionary, source: String, output: int, target: String, input: int) -> void:
	graph["edges"].append({"from":source,"from_port":output,"to":target,"to_port":input})


func wait_frames(count: int = 20) -> void:
	for index: int in range(count):
		OS.delay_msec(2)
		await process_frame


func run() -> void:
	var graph: Dictionary = Model.scene_preset()
	Model.by_kind(graph,"session")["params"]["save_key"] = "ui_role_"+str(Time.get_ticks_usec())
	add(graph,"point","blackboard",{"name":"point","value_type":"vector2","json":"[0,0]"})
	add(graph,"received","event_receive",{"name":"from_role","value_type":"vector2"})
	add(graph,"write_point","set_variable",{"name":"point","value_type":"vector2","json":"[0,0]"})
	edge(graph,"received",0,"write_point",0)
	edge(graph,"received",1,"write_point",1)
	add(graph,"send","event_send",{"name":"to_role","value_type":"vector2","json":"[8,9]"})
	add(graph,"global","blackboard",{"name":"gold","scope":"project","number":3.0})
	add(graph,"write_global","set_variable",{"name":"gold","scope":"project","number":42.0})
	add(graph,"button","button",{"target":"Layout/TestButton","text":"Test","effects_enabled":true,"effect_seconds":0.03})
	add(graph,"ui_event","ui_event",{"target":"Layout/TestButton","signal":"pressed","value_type":"bool"})
	add(graph,"clicked","blackboard",{"name":"clicked","value_type":"bool"})
	add(graph,"click_write","set_variable",{"name":"clicked","value_type":"bool","bool":true})
	edge(graph,"ui_event",0,"click_write",0)
	assert(Builder.create_scene(graph,"res://ui_role.tscn").is_empty())
	var game: Node = (load("res://ui_role.tscn") as PackedScene).instantiate()
	var layout: VBoxContainer = VBoxContainer.new()
	layout.name = "Layout"
	game.add_child(layout)
	var button: Button = Button.new()
	button.name = "TestButton"
	button.text = "Original"
	layout.add_child(button)
	var game_actor: CharacterBody2D = CharacterBody2D.new()
	game_actor.name = "Character"
	game.add_child(game_actor)
	var sprite: AnimatedSprite2D = AnimatedSprite2D.new()
	sprite.sprite_frames = Assets.frames()
	game_actor.add_child(sprite)
	root.add_child(game)
	current_scene = game
	game.call("session_command",0)
	await wait_frames(2)
	var role: Dictionary = RoleModel.empty_graph()
	role["nodes"] = [RoleModel.make_node("receive","receive_event",0,0,{"name":"to_role","scope":"game","value_type":"vector2"}),RoleModel.make_node("send","send_event",100,0,{"name":"from_role","scope":"game","value_type":"vector2","json":"null"})]
	edge(role,"receive",0,"send",0)
	edge(role,"receive",1,"send",1)
	var runtime: RefCounted = RoleRuntime.new()
	assert(runtime.call("setup",role,game_actor,sprite),str(runtime.get("error")))
	game.get("tasks").call("launch","send")
	await wait_frames()
	assert(game.get("variables")["point"] == Vector2(8,9))
	runtime.call("dispose")
	game.get("tasks").call("launch","write_global")
	assert(game.get("services").get("globals")["gold"] == 42.0)
	game.call("session_command",2)
	assert(game.get("services").get("globals")["gold"] == 42.0)
	var features: Node = game.get("features") as Node
	var context: Dictionary = {"messages":{},"values":{},"budget":{"left":512}}
	for native: String in ["Button","TextureButton","Label","RichTextLabel","TextureRect","Panel","PanelContainer","ProgressBar","HSlider","CheckBox","LineEdit","Control"]:
		var node: Dictionary = Model.module("create_"+native,"ui_control",0,0)
		node["params"].merge({"create_type":native,"name":"Native"+native,"operation":"show"},true)
		assert(features.call("start",node,0,context).get("state") == "completed")
		var control: Control = features.get("created_controls")[node["id"]] as Control
		assert(control.is_class(native) and control.visible)
		assert(Access.write(control,"modulate:a",0.5) == "")
		assert(is_equal_approx(float(Access.read(control,"modulate:a")),0.5))
	var image: TextureRect = features.get("created_controls")["create_TextureRect"] as TextureRect
	assert(not Access.write(image,"texture",Assets.frames()).is_empty())
	assert(Access.write(image,"texture",load("res://fixtures/button.png")) == "")
	button.pressed.emit()
	assert(game.get("variables")["clicked"])
	var scale_before: Vector2 = button.scale
	for index: int in range(20):
		button.mouse_entered.emit()
		button.button_down.emit()
		button.button_up.emit()
		button.mouse_exited.emit()
	await wait_frames(20)
	var wrapper: Control = button.get_parent() as Control
	assert(wrapper != layout and wrapper.get_parent() == layout)
	assert(wrapper.scale.is_equal_approx(scale_before))
	game.call("session_command",3)
	button.mouse_entered.emit()
	await wait_frames(20)
	assert(wrapper.scale.is_equal_approx(scale_before*1.1))
	var animations: Node = game.get("animations") as Node
	animations.get_parent().remove_child(animations)
	animations.free()
	await wait_frames(2)
	assert(button.get_parent() == layout and button.scale == scale_before)
	game.set("animations",null)
	game.queue_free()
	current_scene = null
	await wait_frames(2)
	var file: FileAccess = FileAccess.open("res://ui_role-proof.json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"private_role_game_typed_vector_event_roundtrip":true,"global_variables_survive_restart":true,"all_twelve_native_ui_types":true,"safe_property_and_resource_class_validation":true,"ui_signal_executes_graph":true,"rapid_hover_press_container_no_drift_ui_pause_and_layout_restore":true}))
	file.close()
	OS.delay_msec(250)
	quit.call_deferred(0)
