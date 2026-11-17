@tool
extends Node
## One native playback adapter for graph tasks, buttons, audio and previews.
const Binding: GDScript = preload("animation_binding.gd")
const Task: GDScript = preload("blueprint_task.gd")
const Access: GDScript = preload("blueprint_access.gd")
const Link: GDScript = preload("resource_link.gd")
var game: Node
var active: Array[Dictionary] = []
var leases: Dictionary = {}
var wrappers: Dictionary = {}


func setup(controller: Node) -> void:
	game = controller
	process_mode = Node.PROCESS_MODE_ALWAYS


func failed(reason: String) -> RefCounted:
	var task: RefCounted = Task.new()
	task.call("finish", "failed", null, reason)
	return task


func start(p: Dictionary, explicit_target: Node = null) -> RefCounted:
	var target: Node = explicit_target if explicit_target != null else Access.node(game, p.get("target", ""))
	if not is_instance_valid(target) or target.is_queued_for_deletion(): return failed("动画目标不存在")
	if active.size() >= 256: return failed("同时运行的动画已达256项")
	if int(p.get("loops", 1)) == 0 and bool(p.get("wait", true)): return failed("无限循环不能等待结束；请关闭等待或设置有限次数")
	var mode: String = str(p.get("mode", "scale"))
	if mode == "animation" or mode == "frames": return native_animation(target, p, mode)
	var property: String = str(p.get("property", "scale")) if mode == "property" else "position" if mode == "position" else "modulate" if mode == "color" else "scale"
	if target is Control and ((target as Control).get_parent() is Container or wrappers.has(target.get_instance_id())) and property in ["position", "scale", "rotation"]:
		target = motion_target(target as Control)
	if not Access.has_property(target, property): return failed("目标不支持动画属性：" + property)
	var original: Variant = Access.read(target, property)
	var destination: Variant = original
	var beginning: Variant = original
	if mode == "scale":
		if not original is Vector2: return failed("二维缩放需要Control或Node2D")
		destination = original * float(p.get("factor", 1.2))
		if p.get("use_from", false): beginning = Vector2(float(p.get("from_x", 1)), float(p.get("from_y", 1)))
	elif mode == "position":
		if not original is Vector2: return failed("二维位置需要Control或Node2D")
		destination = Vector2(float(p.get("x", 0)), float(p.get("y", 0)))
		if p.get("relative", true): destination += original
		if p.get("use_from", false): beginning = Vector2(float(p.get("from_x", 0)), float(p.get("from_y", 0)))
	elif mode == "color":
		destination = Color(str(p.get("color", "ffffff00")))
		if p.get("use_from", false): beginning = Color(str(p.get("from_color", "ffffffff")))
	elif mode == "property":
		destination = p.get("to", original)
	if typeof(destination) != typeof(original): return failed("动画值类型不符：" + property)
	var key: String = str(target.get_instance_id()) + ":" + property
	if leases.has(key) and leases[key].get("state") == "running":
		if p.get("policy", "replace") == "reject": return failed("同一目标属性已有动画")
		leases[key].call("cancel")
	var task: RefCounted = Task.new()
	leases[key] = task
	if p.get("reverse", false):
		var swap: Variant = beginning
		beginning = destination
		destination = swap
	var tween: Tween = create_tween()
	tween.set_pause_mode(Tween.TWEEN_PAUSE_PROCESS)
	var transition: Variant = p.get("transition", Tween.TRANS_SINE)
	var easing_mode: Variant = p.get("ease", Tween.EASE_IN_OUT)
	tween.set_trans(int({"linear":0,"sine":1,"quad":4,"cubic":7,"back":10,"bounce":9,"elastic":6}.get(transition, 1)) if transition is String else int(transition))
	tween.set_ease(int({"in":0,"out":1,"in_out":2,"out_in":3}.get(easing_mode, 2)) if easing_mode is String else int(easing_mode))
	tween.set_loops(int(p.get("loops", 1)))
	if float(p.get("delay", 0)) > 0: tween.tween_interval(float(p["delay"]))
	tween.tween_property(target, NodePath(property), destination, maxf(0.001, float(p.get("seconds", 0.25)))).from(beginning)
	if p.get("pingpong", false): tween.tween_property(target, NodePath(property), beginning, maxf(0.001, float(p.get("seconds", 0.25))))
	tween.finished.connect(func() -> void: task.call("finish", "completed"), CONNECT_ONE_SHOT)
	var target_ref: WeakRef = weakref(target)
	task.get("cleanup").append(func() -> void:
		var subject: Node = target_ref.get_ref() as Node
		if tween.is_valid(): tween.kill()
		if leases.get(key) == task: leases.erase(key)
		if p.get("restore", false) and subject != null: subject.set_indexed(NodePath(property), original))
	active.append({"task":task,"target":target,"tween":tween,"ui":bool(p.get("ui", false)),"paused":false,"elapsed":0.0,"timeout":float(p.get("timeout", 120)) if int(p.get("loops", 1)) != 0 else 0.0})
	return task


func native_animation(target: Node, p: Dictionary, mode: String) -> RefCounted:
	var key: String = str(target.get_instance_id()) + ":native"
	if leases.has(key) and leases[key].get("state") == "running":
		if p.get("policy", "replace") == "reject": return failed("目标已有动画播放任务")
		leases[key].call("cancel")
	var loops: int = int(p.get("loops", 1))
	var clip: String = str(p.get("clip", ""))
	var task: RefCounted = Task.new()
	var record: Dictionary = {"task":task,"target":target,"ui":bool(p.get("ui", false)),"paused":false,"elapsed":0.0,"timeout":float(p.get("timeout", 120)) if loops != 0 else 0.0,"remaining":loops}
	if mode == "frames":
		var sprite: AnimatedSprite2D = target as AnimatedSprite2D
		if sprite == null: return failed("SpriteFrames目标需要AnimatedSprite2D")
		var resource: Resource = load(str(p["frames"])) if not str(p.get("frames", "")).is_empty() else sprite.sprite_frames
		var frames: SpriteFrames = Link.frames(resource)
		if frames == null: return failed("缺少SpriteFrames")
		if clip.is_empty() and not frames.get_animation_names().is_empty(): clip = str(frames.get_animation_names()[0])
		if not frames.has_animation(clip) or frames.get_frame_count(clip) == 0: return failed("帧动画不存在或没有帧：" + clip)
		var old: SpriteFrames = sprite.sprite_frames
		var old_speed: float = sprite.speed_scale
		var old_clip: StringName = sprite.animation
		var old_frame: int = sprite.frame
		var old_playing: bool = sprite.is_playing()
		sprite.sprite_frames = frames.duplicate(true) as SpriteFrames
		sprite.sprite_frames.set_animation_loop(clip, loops == 0)
		sprite.speed_scale = float(p.get("speed", 1))
		var callback: Callable = func() -> void:
			record["remaining"] = int(record["remaining"]) - 1
			if int(record["remaining"]) <= 0: task.call("finish", "completed")
			else: Binding.play(sprite,clip,-1.0 if p.get("reverse",false) else 1.0,bool(p.get("reverse",false)))
		sprite.animation_finished.connect(callback)
		Binding.play(sprite,clip,-1.0 if p.get("reverse",false) else 1.0,bool(p.get("reverse",false)))
		record["sprite"] = sprite
		var sprite_ref: WeakRef = weakref(sprite)
		task.get("cleanup").append(func() -> void:
			var current: AnimatedSprite2D = sprite_ref.get_ref() as AnimatedSprite2D
			if current != null:
				if current.animation_finished.is_connected(callback): current.animation_finished.disconnect(callback)
				current.pause()
				current.speed_scale = old_speed
				if p.get("restore", false):
					current.sprite_frames = old
					current.animation = old_clip
					current.frame = old_frame
					if old_playing: current.play())
	else:
		var player: AnimationPlayer = target as AnimationPlayer
		var made: bool = false
		if player == null:
			player = target.get_node_or_null(NodePath(str(p.get("player", "AnimationPlayer")))) as AnimationPlayer
		if player == null:
			player = AnimationPlayer.new()
			player.name = "AlIAnimationPlayer"
			target.add_child(player)
			made = true
		var source: Animation
		var resource: Resource = load(str(p["animation"])) if not str(p.get("animation", "")).is_empty() else null
		if resource is Animation: source = resource as Animation
		elif resource is AnimationLibrary:
			var source_library: AnimationLibrary = resource as AnimationLibrary
			if clip.is_empty() and not source_library.get_animation_list().is_empty(): clip = str(source_library.get_animation_list()[0])
			source = source_library.get_animation(clip) if source_library.has_animation(clip) else null
		elif player.has_animation(clip): source = player.get_animation(clip)
		if source == null:
			if made: player.queue_free()
			return failed("找不到动画资源或片段：" + clip)
		var copy: Animation = source.duplicate(true) as Animation
		copy.loop_mode = Animation.LOOP_LINEAR if loops == 0 else Animation.LOOP_NONE
		var binding: Node = player.get_node_or_null(player.root_node)
		var path_map: Variant = JSON.parse_string(str(p.get("remap", "{}")))
		if not path_map is Dictionary: path_map = {}
		var snapshots: Array[Dictionary] = []
		for track: int in range(copy.get_track_count()):
			if p.get("_preview",false) and copy.track_get_type(track) != Animation.TYPE_VALUE:
				if made: player.queue_free()
				return failed("独立预览只执行白名单属性轨道；方法、音频与其它轨道请在游戏运行时验证")
			var path: NodePath = copy.track_get_path(track)
			var old_path: String = str(path.get_concatenated_names())
			var new_path: String = str(path_map.get(old_path, old_path))
			if p.get("retarget", false): new_path = "."
			var destination: Node = binding.get_node_or_null(NodePath(new_path)) if binding != null else null
			if destination == null or not (game == destination or game.is_ancestor_of(destination)):
				if made: player.queue_free()
				return failed("动画轨道目标无效，请重映射：" + old_path)
			var subnames: String = str(path.get_concatenated_subnames())
			if copy.track_get_type(track) == Animation.TYPE_VALUE and not subnames.is_empty() and not Access.has_property(destination, subnames):
				if made: player.queue_free()
				return failed("动画轨道属性不适用：" + subnames)
			if copy.track_get_type(track) == Animation.TYPE_VALUE and not subnames.is_empty(): snapshots.append({"node":destination,"property":subnames,"value":Access.read(destination, subnames)})
			copy.track_set_path(track, NodePath(new_path + (":" + subnames if not subnames.is_empty() else "")))
		var library: AnimationLibrary = AnimationLibrary.new()
		library.add_animation(&"clip", copy)
		var library_name: String = "ali_task_" + str(task.get_instance_id())
		player.add_animation_library(library_name, library)
		var full_clip: String = library_name + "/clip"
		var old_speed: float = player.speed_scale
		var old_clip: StringName = player.assigned_animation
		var old_position: float = player.current_animation_position if not player.current_animation.is_empty() else 0.0
		var old_playing: bool = player.is_playing()
		var callback: Callable = func(clip_name: StringName) -> void:
			if clip_name != full_clip: return
			record["remaining"] = int(record["remaining"]) - 1
			if int(record["remaining"]) <= 0: task.call("finish", "completed")
			else: player.play(full_clip, -1, -1.0 if p.get("reverse", false) else 1.0, bool(p.get("reverse", false)))
		player.animation_finished.connect(callback)
		player.speed_scale = maxf(0.01, float(p.get("speed", 1)))
		player.play(full_clip, -1, -1.0 if p.get("reverse", false) else 1.0, bool(p.get("reverse", false)))
		record["player"] = player
		var player_ref: WeakRef = weakref(player)
		task.get("cleanup").append(func() -> void:
			var current: AnimationPlayer = player_ref.get_ref() as AnimationPlayer
			if current != null:
				if current.animation_finished.is_connected(callback): current.animation_finished.disconnect(callback)
				current.stop(true)
				current.speed_scale = old_speed
				current.remove_animation_library(library_name)
				if made: current.queue_free()
				elif p.get("restore", false) and current.has_animation(old_clip):
					current.play(old_clip)
					current.seek(old_position, true)
					if not old_playing: current.pause()
			if p.get("restore", false):
				for snapshot: Dictionary in snapshots:
					if is_instance_valid(snapshot["node"]): Access.write(snapshot["node"], snapshot["property"], snapshot["value"]))
	leases[key] = task
	task.get("cleanup").append(func() -> void:
		if leases.get(key) == task: leases.erase(key))
	active.append(record)
	return task


func motion_target(control: Control) -> Control:
	var id: int = control.get_instance_id()
	if wrappers.has(id) and is_instance_valid(wrappers[id]["wrapper"]): return wrappers[id]["wrapper"] as Control
	var parent: Container = control.get_parent() as Container
	if parent == null: return control
	var wrapper: Control = Control.new()
	wrapper.name = str(control.name) + "Motion"
	wrapper.custom_minimum_size = control.get_combined_minimum_size()
	wrapper.size_flags_horizontal = control.size_flags_horizontal
	wrapper.size_flags_vertical = control.size_flags_vertical
	wrapper.size_flags_stretch_ratio = control.size_flags_stretch_ratio
	wrapper.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var index: int = control.get_index()
	var layout: Dictionary = {}
	for property: String in ["anchor_left","anchor_top","anchor_right","anchor_bottom","offset_left","offset_top","offset_right","offset_bottom","position","size"]: layout[property] = control.get(property)
	parent.add_child(wrapper)
	parent.move_child(wrapper, index)
	control.reparent(wrapper, false)
	control.position = Vector2.ZERO
	control.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	control.set_meta("ali_motion_wrapper",weakref(wrapper))
	wrappers[id] = {"target":control,"wrapper":wrapper,"parent":parent,"index":index,"layout":layout}
	return wrapper


func command(target: Node, operation: String) -> bool:
	var wrapper: Node = wrappers[target.get_instance_id()]["wrapper"] as Node if is_instance_valid(target) and wrappers.has(target.get_instance_id()) else null
	var found: bool = false
	for row: Dictionary in active:
		if row["target"] != target and row["target"] != wrapper: continue
		if operation == "stop": row["task"].call("cancel")
		else:
			row["manual_pause"] = operation == "pause"
			set_paused(row, operation == "pause")
		found = true
	return found


func shake(camera: Camera2D, strength: float, seconds: float, ui: bool) -> RefCounted:
	if not is_instance_valid(camera): return failed("相机不存在")
	var key: String = str(camera.get_instance_id()) + ":offset"
	if leases.has(key): leases[key].call("cancel")
	var original: Vector2 = camera.offset
	var camera_ref: WeakRef = weakref(camera)
	var task: RefCounted = Task.new()
	leases[key] = task
	var tween: Tween = create_tween()
	tween.set_pause_mode(Tween.TWEEN_PAUSE_PROCESS)
	tween.tween_method(func(amplitude: float) -> void:
		var current: Camera2D = camera_ref.get_ref() as Camera2D
		if current != null: current.offset = original + Vector2(randf_range(-amplitude,amplitude),randf_range(-amplitude,amplitude)), strength, 0.0, maxf(seconds,0.001))
	tween.finished.connect(func() -> void: task.call("finish"), CONNECT_ONE_SHOT)
	task.get("cleanup").append(func() -> void:
		if tween.is_valid(): tween.kill()
		var current: Camera2D = camera_ref.get_ref() as Camera2D
		if current != null: current.offset = original
		if leases.get(key) == task: leases.erase(key))
	active.append({"task":task,"target":camera,"tween":tween,"ui":ui,"paused":false,"elapsed":0.0,"timeout":seconds+1.0})
	return task


func set_paused(row: Dictionary, paused: bool) -> void:
	if row["paused"] == paused: return
	row["paused"] = paused
	if row.has("tween"):
		var tween: Tween = row["tween"]
		if tween.is_valid():
			if paused: tween.pause()
			else: tween.play()
	if row.has("player") and is_instance_valid(row["player"]):
		if paused: row["player"].pause()
		else: row["player"].play()
	if row.has("sprite") and is_instance_valid(row["sprite"]):
		if paused: row["sprite"].pause()
		else: row["sprite"].play()


func _process(delta: float) -> void:
	for row: Dictionary in active.duplicate():
		if row["task"].get("state") != "running":
			active.erase(row)
			continue
		if not is_instance_valid(row["target"]) or row["target"].is_queued_for_deletion():
			row["task"].call("finish", "failed", null, "动画目标已删除")
			continue
		var paused: bool = bool(row.get("manual_pause", false)) or game.get("state") == "paused" and not row["ui"]
		set_paused(row, paused)
		if not paused: row["elapsed"] = float(row["elapsed"]) + delta
		if float(row["timeout"]) > 0 and float(row["elapsed"]) > float(row["timeout"]): row["task"].call("finish", "failed", null, "动画任务超时")


func cancel_all() -> void:
	for row: Dictionary in active.duplicate(): row["task"].call("cancel")
	active.clear()
	leases.clear()


func _exit_tree() -> void:
	cancel_all()
	for row: Dictionary in wrappers.values():
		if is_instance_valid(row["target"]) and is_instance_valid(row["parent"]):
			row["target"].reparent(row["parent"], false)
			row["parent"].move_child(row["target"], mini(int(row["index"]), row["parent"].get_child_count() - 1))
			row["target"].remove_meta("ali_motion_wrapper")
			for property: String in row["layout"]: row["target"].set(property,row["layout"][property])
		if is_instance_valid(row["wrapper"]): row["wrapper"].queue_free()
	wrappers.clear()
