extends Node
## Native 2D/non-positional audio, reusing the game's scoped buses and Tween.
const Task: GDScript = preload("blueprint_task.gd")
var game: Node
var voices: Dictionary = {}
var waiting: Array[Dictionary] = []
var manual_pause: Dictionary = {}


func setup(controller: Node) -> void:
	game = controller
	process_mode = Node.PROCESS_MODE_ALWAYS


func result(error: String = "") -> RefCounted:
	var task: RefCounted = Task.new()
	task.call("finish","completed" if error.is_empty() else "failed",null,error)
	return task


func execute(id: String, p: Dictionary, port: int) -> RefCounted:
	var voice: Node = voices.get(id) as Node
	if port in [0,4] and voice == null:
		if str(p["path"]).is_empty(): return result("请选择音频文件")
		var stream: AudioStream = load(str(p["path"])) as AudioStream
		if stream == null: return result("资源不是可播放音频")
		stream = stream.duplicate(true) as AudioStream
		var native_loop: bool = false
		if stream is AudioStreamWAV:
			stream.loop_mode = AudioStreamWAV.LOOP_DISABLED
			if p["loop"]:
				if stream.loop_end <= stream.loop_begin:
					stream.loop_begin = 0
					stream.loop_end = roundi(stream.get_length() * stream.mix_rate)
				stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
				native_loop = true
		elif stream is AudioStreamMP3 or stream is AudioStreamOggVorbis:
			stream.set("loop",p["loop"])
			native_loop = bool(p["loop"])
		if p["spatial"]:
			voice = AudioStreamPlayer2D.new()
			(voice as AudioStreamPlayer2D).position = Vector2(float(p["x"]),float(p["y"]))
		else: voice = AudioStreamPlayer.new()
		voice.name = "Voice_" + id
		voice.set("stream",stream)
		voice.set_meta("ali_ui",p["channel"] == "UI")
		voice.set("bus",str(game.get("bus_names")[p["channel"]]))
		voice.set("volume_db",float(p["volume"]))
		voice.process_mode = Node.PROCESS_MODE_ALWAYS if p["channel"] == "UI" else Node.PROCESS_MODE_INHERIT
		add_child(voice)
		voices[id] = voice
		voice.connect("finished",func() -> void:
			if p["loop"] and not native_loop and is_instance_valid(voice): voice.call("play"))
	if voice == null: return result("此音频尚未播放")
	match port:
		0:
			if p["loop"] and p["wait"]: return result("循环音频不能等待自然结束")
			game.get("animations").call("command",voice,"stop")
			manual_pause[id] = false
			voice.set("volume_db",float(p["volume"]))
			voice.set("stream_paused",false)
			voice.call("play")
			if not p["wait"]: return result()
			var task: RefCounted = Task.new()
			var callback: Callable = func() -> void: task.call("finish")
			voice.connect("finished",callback,CONNECT_ONE_SHOT)
			var voice_ref: WeakRef = weakref(voice)
			task.get("cleanup").append(func() -> void:
				var current: Node = voice_ref.get_ref() as Node
				if current != null:
					if current.is_connected("finished",callback): current.disconnect("finished",callback)
					if task.get("state") != "completed": current.call("stop"))
			waiting.append({"task":task,"voice":voice,"elapsed":0.0,"timeout":float(p["timeout"]),"ui":p["channel"] == "UI"})
			return task
		1:
			game.get("animations").call("command",voice,"stop")
			voice.call("stop")
			for row: Dictionary in waiting:
				if row["voice"] == voice: row["task"].call("cancel")
		2: manual_pause[id] = true; voice.set("stream_paused",true)
		3: manual_pause[id] = false; voice.set("stream_paused",false)
		4:
			manual_pause[id] = false
			voice.set("stream_paused",false)
			voice.set("volume_db",-60.0)
			voice.call("play")
			return game.get("animations").call("start",{"mode":"property","property":"volume_db","to":float(p["volume"]),"seconds":p["seconds"],"ui":p["channel"] == "UI"},voice) as RefCounted
		5:
			var task: RefCounted = game.get("animations").call("start",{"mode":"property","property":"volume_db","to":-60.0,"seconds":p["seconds"],"ui":p["channel"] == "UI"},voice) as RefCounted
			var voice_ref: WeakRef = weakref(voice)
			task.connect("settled",func(state: String,_value: Variant) -> void:
				var current: Node = voice_ref.get_ref() as Node
				if state == "completed" and current != null: current.call("stop"),CONNECT_ONE_SHOT)
			return task
	return result()


func _process(delta: float) -> void:
	for id: String in voices:
		var voice: Node = voices[id] as Node
		if is_instance_valid(voice): voice.set("stream_paused",bool(manual_pause.get(id,false)) or game.get("state") == "paused" and not voice.get_meta("ali_ui",false))
	for row: Dictionary in waiting.duplicate():
		if row["task"].get("state") != "running": waiting.erase(row); continue
		if not is_instance_valid(row["voice"]): row["task"].call("finish","failed",null,"音频节点已删除"); continue
		if row["voice"].get("stream_paused") or game.get("state") == "paused" and not row["ui"]: continue
		row["elapsed"] = float(row["elapsed"])+delta
		if float(row["elapsed"]) > float(row["timeout"]): row["task"].call("finish","failed",null,"等待音频结束超时")


func _exit_tree() -> void:
	for row: Dictionary in waiting: row["task"].call("cancel")
	for voice: Node in voices.values():
		if is_instance_valid(voice): voice.call("stop")
	waiting.clear()
	voices.clear()
	manual_pause.clear()
