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


func cancel() -> void:
	if active != null: active.call("cancel")


func _exit_tree() -> void:
	cancel()
	cache.clear()
