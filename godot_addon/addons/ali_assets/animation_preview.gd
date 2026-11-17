@tool
extends Window
## Clone native visual properties only. Never instantiate user scripts/scenes.
const World: GDScript = preload("preview_world.gd")
const Access: GDScript = preload("blueprint_access.gd")
const Model: GDScript = preload("game_model.gd")
const SAFE: Array[String] = ["Node","Node2D","Control","Sprite2D","AnimatedSprite2D","Camera2D","AnimationPlayer","CanvasLayer","TextureRect","ColorRect","Button","TextureButton","Label","RichTextLabel","Panel","PanelContainer","HBoxContainer","VBoxContainer","GridContainer","CenterContainer","MarginContainer","ProgressBar","HSlider","CheckBox","LineEdit","TileMapLayer","Parallax2D","Polygon2D"]
var source: Node
var params: Dictionary
var kind: String
var viewport: SubViewport
var world: Node2D
var task: RefCounted
var note: Label


func _init() -> void:
	visible = false
	force_native = true


func present(root: Node, node: Dictionary) -> void:
	source = root
	params = node["params"].duplicate(true)
	kind = str(node["kind"])
	title = "AlI · 动画／Camera2D独立预览"
	size = Vector2i(1000,680)
	close_requested.connect(func() -> void: stop(); queue_free())
	var box: VBoxContainer = VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(box)
	note = Label.new()
	note.text = "原生可视节点副本 · 不运行用户脚本 · 停止／关闭销毁副本，原场景保持原状"
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(note)
	var host: SubViewportContainer = SubViewportContainer.new()
	host.stretch = true
	host.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(host)
	viewport = SubViewport.new()
	viewport.size = Vector2i(960,540)
	viewport.disable_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	host.add_child(viewport)
	var controls: HBoxContainer = HBoxContainer.new()
	box.add_child(controls)
	for action: Array in [["▶ 播放／重播",play],["Ⅱ 暂停／恢复",pause],["■ 停止／复位",stop]]:
		var button: Button = Button.new()
		button.text = action[0]
		button.pressed.connect(action[1])
		controls.add_child(button)
	reset_world()
	popup_centered_clamped(Vector2i(1000,680),0.8)


static func clone_visual(original: Node) -> Node:
	var target: Node = ClassDB.instantiate(original.get_class()) as Node if original.get_class() in SAFE else Node2D.new()
	target.name = original.name
	for row: Dictionary in original.get_property_list():
		var property: String = str(row["name"])
		if property in ["owner","script","process_mode","unique_name_in_owner"] or not (int(row["usage"]) & PROPERTY_USAGE_STORAGE): continue
		if not property in Access.PROPERTIES and not property in ["centered","offset","region_enabled","region_rect","texture_filter","texture_repeat","polygon","color","flip_h","flip_v","stretch_mode","expand_mode","anchor_left","anchor_right","anchor_top","anchor_bottom","offset_left","offset_right","offset_top","offset_bottom","size_flags_horizontal","size_flags_vertical","root_node","parameters/playback"]: continue
		if not property_exists(target,property): continue
		var value: Variant = original.get(property)
		if value is Resource: value = value.duplicate(true)
		target.set(property,value)
	if target is AnimationPlayer and original is AnimationPlayer:
		for library: StringName in original.get_animation_library_list(): target.add_animation_library(library,original.get_animation_library(library).duplicate(true))
	for child: Node in original.get_children(): target.add_child(clone_visual(child))
	return target


static func property_exists(target: Node, name: String) -> bool:
	for row: Dictionary in target.get_property_list():
		if str(row["name"]) == name: return true
	return false


func reset_world() -> void:
	if is_instance_valid(world):
		world.get("animations").call("cancel_all")
		viewport.remove_child(world)
		world.free()
	world = World.new()
	world.name = "PreviewWorld"
	viewport.add_child(world)
	if is_instance_valid(source):
		# Use world itself as root so paths relative to the game remain valid.
		for child: Node in source.get_children(): world.add_child(clone_visual(child))
	if Access.node(world,params.get("target","")) == null:
		if kind == "camera2d":
			var camera: Camera2D = Camera2D.new()
			camera.name = "PreviewCamera"
			world.add_child(camera)
			camera.position = Vector2(480,270)
			params["target"] = "PreviewCamera"
		else:
			var ghost: ColorRect = ColorRect.new()
			ghost.name = "PreviewTarget"
			ghost.position = Vector2(420,220)
			ghost.size = Vector2(120,100)
			ghost.color = Color("66b6de")
			world.add_child(ghost)
			params["target"] = "PreviewTarget"
	if kind == "camera2d":
		for index: int in range(20):
			var marker: ColorRect = ColorRect.new()
			marker.position = Vector2((index%5)*200,floori(float(index)/5.0)*150)
			marker.size = Vector2(100,70)
			marker.color = Color.from_hsv(float(index)/20,0.6,0.8)
			world.add_child(marker)


func play() -> void:
	reset_world()
	params["_preview"] = true
	params["wait"] = false if int(params.get("loops",1)) == 0 else true
	if kind == "camera2d": task = world.get("world_tools").call("camera",params,0) as RefCounted
	else: task = world.get("animations").call("start",params) as RefCounted
	note.text = str(task.get("detail")) if task.get("state") == "failed" else "播放中 · 副本隔离，停止复位"


func pause() -> void:
	if not is_instance_valid(world): return
	world.set("state","running" if world.get("state") == "paused" else "paused")


func stop() -> void:
	if task != null: task.call("cancel")
	reset_world()
	note.text = "已复位副本 · 原场景和资源保持原状"
