extends Node
## Persistent native scene transition; an old scene cannot cancel its fade-in.
const Task: GDScript = preload("blueprint_task.gd")
const Animations: GDScript = preload("game_animations.gd")
var service: Node
var animations: Node
var layer: CanvasLayer
var cover: ColorRect
var active: RefCounted
var cache: Dictionary = {}
var overlays: Array[Dictionary] = []


func setup(controller: Node) -> void:
	service = controller
	process_mode = Node.PROCESS_MODE_ALWAYS
	animations = Animations.new()
	add_child(animations)
	animations.call("setup", service)
	layer = CanvasLayer.new()
	layer.layer = 1000
	add_child(layer)
	cover = ColorRect.new()
	cover.color = Color.BLACK
	cover.modulate.a = 0
	cover.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(cover)
	cover.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)


func request(path: String, fade: float = 0.3, preload_only: bool = false) -> RefCounted:
	var task: RefCounted = Task.new()
	if not path.begins_with("res://") or ".." in path or not ResourceLoader.exists(path):
		task.call("finish","failed",null,"请选择当前项目内有效场景")
		return task
	if not preload_only:
		if active != null and active.get("state") == "running": active.call("cancel")
		active = task
		task.get("cleanup").append(func() -> void:
			if active == task:
				cover.modulate.a = 0
				cover.mouse_filter = Control.MOUSE_FILTER_IGNORE)
	perform.call_deferred(task,path,fade,preload_only)
	return task


func perform(task: RefCounted, path: String, fade: float, preload_only: bool) -> void:
	var packed: PackedScene = cache.get(path) as PackedScene
	if packed == null:
		var error: Error = ResourceLoader.load_threaded_request(path,"PackedScene")
		if error not in [OK,ERR_BUSY]: task.call("finish","failed",null,"场景预加载请求失败"); return
		var started: int = Time.get_ticks_msec()
		while task.get("state") == "running":
			var status: ResourceLoader.ThreadLoadStatus = ResourceLoader.load_threaded_get_status(path)
			if status == ResourceLoader.THREAD_LOAD_LOADED:
				packed = ResourceLoader.load_threaded_get(path) as PackedScene
				break
			if status in [ResourceLoader.THREAD_LOAD_FAILED,ResourceLoader.THREAD_LOAD_INVALID_RESOURCE] or Time.get_ticks_msec()-started > 120000:
				task.call("finish","failed",null,"场景预加载失败或超时")
				return
			await get_tree().process_frame
	if task.get("state") != "running": return
	if packed == null: task.call("finish","failed",null,"资源不是PackedScene"); return
	cache[path] = packed
	if preload_only: task.call("finish","completed",path); return
	cover.mouse_filter = Control.MOUSE_FILTER_STOP
	if fade > 0:
		var out: RefCounted = animations.call("start",{"mode":"property","property":"modulate:a","to":1.0,"seconds":fade,"ui":true},cover) as RefCounted
		task.get("children").append(out)
		if out.get("state") == "running": await out.settled
	if task.get("state") != "running": return
	service.call("notify","scene_exiting",{"scene":get_tree().current_scene.scene_file_path if get_tree().current_scene != null else "","next_scene":path})
	task.set("persistent",true)
	get_tree().paused = false
	var changed: Error = get_tree().change_scene_to_packed(packed)
	if changed != OK: task.call("finish","failed",null,"场景切换失败"); return
	clear_overlays()
	await get_tree().scene_changed
	await get_tree().process_frame
	if task.get("state") != "running": return
	var restored: RefCounted = service.call("restore_pending") as RefCounted
	if restored.get("state") == "running": await restored.settled
	if restored.get("state") == "failed": task.call("finish","failed",null,str(restored.get("detail"))); return
	service.call("notify","scene_entered",{"scene":path})
	if fade > 0:
		var fade_in: RefCounted = animations.call("start",{"mode":"property","property":"modulate:a","to":0.0,"seconds":fade,"ui":true},cover) as RefCounted
		task.get("children").append(fade_in)
		if fade_in.get("state") == "running": await fade_in.settled
	if task.get("state") == "running": task.call("finish","completed",path)


func request_overlay(path: String, pause_world: bool) -> RefCounted:
	var task: RefCounted = Task.new()
	perform_overlay.call_deferred(task, path, pause_world)
	return task


func perform_overlay(task: RefCounted, path: String, pause_world: bool) -> void:
	if task.get("state") != "running": return
	var error: String = open_overlay(path, pause_world)
	task.call("finish", "completed" if error.is_empty() else "failed", null, error)


func open_overlay(path: String, pause_world: bool) -> String:
	if not path.begins_with("res://") or ".." in path or not ResourceLoader.exists(path, "PackedScene"):
		return "请选择当前项目内有效的界面场景"
	if get_tree().current_scene == null or path == get_tree().current_scene.scene_file_path:
		return "叠加界面必须是独立场景"
	if overlays.size() >= 8 or overlays.any(func(row: Dictionary) -> bool: return row["path"] == path):
		return "该界面已打开或达到叠加上限"
	var packed: PackedScene = load(path) as PackedScene
	if packed == null: return "无法读取界面场景"
	var panel: Node = packed.instantiate()
	if not panel is Control and not panel is Node2D:
		panel.free()
		return "界面根节点需要 Control 或 Node2D"
	var focus: Control = get_viewport().gui_get_focus_owner()
	if focus != null: focus.release_focus()
	if not overlays.is_empty(): show_overlay_layer(overlays.back()["layer"], false)
	var layer_ui: CanvasLayer = CanvasLayer.new()
	layer_ui.name = "BlueprintOverlay"
	layer_ui.layer = 100 + overlays.size()
	add_child(layer_ui, true)
	var shade: ColorRect = ColorRect.new()
	shade.color = Color(0.04, 0.06, 0.08, 0.78)
	shade.mouse_filter = Control.MOUSE_FILTER_STOP
	layer_ui.add_child(shade)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel.set_meta(&"ali_blueprint_overlay", true)
	layer_ui.add_child(panel)
	if panel is Control: panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var owns_pause: bool = pause_world and not get_tree().paused
	overlays.append({"path":path, "layer":layer_ui, "panel":panel, "resume":owns_pause, "focus":weakref(focus) if focus != null else null})
	if owns_pause: service.call("lifecycle", "pause")
	return ""


func show_overlay_layer(layer_ui: CanvasLayer, active_layer: bool) -> void:
	layer_ui.visible = active_layer
	layer_ui.process_mode = Node.PROCESS_MODE_ALWAYS if active_layer else Node.PROCESS_MODE_DISABLED


func close_overlay(caller: Node) -> String:
	if overlays.is_empty() or overlays.back()["panel"] != caller:
		return "请从当前叠加界面的蓝图关闭它"
	var row: Dictionary = overlays.pop_back()
	show_overlay_layer(row["layer"], false)
	row["layer"].queue_free()
	if not overlays.is_empty(): show_overlay_layer(overlays.back()["layer"], true)
	if row["resume"]: service.call("lifecycle", "resume")
	var focus_ref: WeakRef = row["focus"] as WeakRef
	var focus: Control = focus_ref.get_ref() as Control if focus_ref != null else null
	if is_instance_valid(focus): focus.grab_focus.call_deferred()
	return ""


func clear_overlays() -> void:
	for row: Dictionary in overlays:
		show_overlay_layer(row["layer"], false)
		row["layer"].queue_free()
	overlays.clear()


func cancel() -> void:
	if active != null: active.call("cancel")


func _exit_tree() -> void:
	cancel()
	overlays.clear()
	cache.clear()
