extends Node
## Composition root: persistence, InputMap and scenes remain separate adapters.
const InputManager: GDScript = preload("framework_input.gd")
const Storage: GDScript = preload("framework_storage.gd")
const Scenes: GDScript = preload("framework_scenes.gd")
const Types: GDScript = preload("blueprint_types.gd")
const Access: GDScript = preload("blueprint_access.gd")
const Events: GDScript = preload("blueprint_events.gd")
const Task: GDScript = preload("blueprint_task.gd")
const Scope: GDScript = preload("subgraph_runtime.gd")
const Model: GDScript = preload("game_model.gd")
var key: String = ""
var manifest: Dictionary = {}
var state: String = "menu"
var game_ref: WeakRef
var inputs: Node
var scenes: Node
var storage: RefCounted
var bus: Node
var settings: Dictionary = {}
var settings_saved: bool = false
var globals: Dictionary = {}
var registered: Dictionary = {}
var pending_save: Dictionary = {}
var restore_task: RefCounted
var last_error: String = ""
var owns_pause: bool = false
var subgraph_jobs: Array[Dictionary] = []


static func obtain(tree: SceneTree, config: Dictionary, fallback: String, script: GDScript) -> Node:
	var identifier: String = str(config.get("key",fallback))
	for service: Node in tree.get_nodes_in_group("ali_framework_services"):
		if service.get("key") == identifier: return service
	var service: Node = script.new()
	service.set("key",identifier)
	service.set("manifest",config.duplicate(true))
	service.name = "AlIFramework_" + identifier
	tree.root.add_child(service)
	service.add_to_group("ali_framework_services")
	service.call("configure")
	return service


func configure() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	storage = Storage.new()
	last_error = str(storage.call("configure",key))
	inputs = InputManager.new()
	inputs.name = "InputManager"
	add_child(inputs)
	inputs.connect("capture_finished",func(_action: String,error: String) -> void:
		last_error = error
		if error.is_empty(): save_settings())
	scenes = Scenes.new()
	scenes.name = "SceneManager"
	add_child(scenes)
	scenes.call("setup",self)
	bus = Events.obtain(get_tree(),Events)
	var loaded: Dictionary = storage.call("read_settings")
	if loaded.has("error"): last_error = str(loaded["error"])
	else:
		settings = loaded
		settings_saved = not loaded.is_empty()
	if settings.get("bindings") is Dictionary:
		var error: String = inputs.call("restore",settings["bindings"])
		if not error.is_empty(): last_error = error
	if manifest.get("native_menus",false):
		if not settings.has("volumes"): settings["volumes"] = {"Master":0.0,"BGM":-12.0,"SFX":-4.0,"UI":-8.0}
		if not settings.has("resolution"): settings["resolution"] = [960,540]
		if not settings.has("window"): settings["window"] = "windowed"
		var error: String = apply_settings()
		if not error.is_empty(): last_error = error


func current_game() -> Node:
	return game_ref.get_ref() as Node if game_ref != null else null


func attach_game(game: Node, apply_initial_settings: bool = true) -> void:
	game_ref = weakref(game)
	if not settings.has("volumes"): settings["volumes"] = game.get("mixer_values").duplicate(true)
	if not settings.has("resolution"):
		var resolution: Vector2i = get_window().size
		if resolution.x < 320 or resolution.y < 240: resolution = game.get("base_size")
		settings["resolution"] = [resolution.x,resolution.y]
	if not settings.has("window"): settings["window"] = "windowed"
	if apply_initial_settings:
		var error: String = apply_settings()
		if not error.is_empty(): last_error = error
	elif settings_saved:
		apply_audio_settings(game, settings["volumes"])
	notify("initialized",{"state":state})
	var transition: RefCounted = scenes.get("active") as RefCounted
	var scene: Node = game.get("binding_root") as Node if "binding_root" in game and game.get("binding_root") != null else game
	if transition == null or transition.get("state") != "running": notify("scene_entered",{"scene":scene.scene_file_path})
	if not pending_save.is_empty(): restore_pending.call_deferred()
	elif manifest.get("auto_start",false): lifecycle.call_deferred("start")


func detach_game(game: Node) -> void:
	if current_game() == game:
		game_ref = null
		if owns_pause: get_tree().paused = false; owns_pause = false


func notify(event: String, data: Variant = null) -> void:
	if bus != null: bus.call("send","project:" + key,event,data if data != null else {"state":state})


func done(error: String = "", value: Variant = null) -> RefCounted:
	last_error = error
	var task: RefCounted = Task.new()
	task.call("finish","completed" if error.is_empty() else "failed",value,error)
	return task


func execute(game: Node, node: Dictionary, port: int, context: Dictionary) -> RefCounted:
	var p: Dictionary = node["params"]
	var id: String = str(node["id"])
	var kind: String = str(node["kind"])
	match kind:
		"subgraph": return run_subgraph(game,node,context)
		"audio_fx": return game.get("audio_tools").call("execute",id,p,port) as RefCounted
		"input_bind":
			var error: String = ""
			match str(p["operation"]):
				"reset": inputs.call("reset",str(p["action"]))
				"capture": inputs.call("begin_capture",str(p["action"]),str(p["conflict"]))
				"save": error = save_settings()
				_:
					var rows: Variant = JSON.parse_string(str(p["bindings"]))
					error = str(inputs.call("rebind",str(p["action"]),rows,str(p["conflict"]),p["operation"] == "add")) if rows is Array else "键位需要JSON数组"
			if error.is_empty() and p["operation"] != "capture": error = save_settings()
			return done(error)
		"game_service": return lifecycle(str(p["operation"]))
		"scene_service":
			if port == 1: scenes.call("cancel"); return done()
			var path: String = str(p["scene"])
			if p["operation"] == "open_overlay":
				return scenes.call("request_overlay", path, bool(p.get("pause_world", false))) as RefCounted
			if p["operation"] == "close_overlay":
				return done(str(scenes.call("close_overlay", game.get("binding_root"))))
			if p["operation"] == "reload": path = get_tree().current_scene.scene_file_path if get_tree().current_scene != null else game.scene_file_path
			elif p["operation"] == "menu": path = str(manifest.get("menu_scene",""))
			return scenes.call("request",path,float(p["fade"]),p["operation"] == "preload") as RefCounted
		"settings_service":
			var error: String = settings_operation(p,float(game.get("program").call("input_value",id,1,p["number"])))
			publish(game,id,settings.duplicate(true),context)
			return done(error)
		"data_register":
			var value: Variant = game.get("program").call("input_value",id,1,Types.initial(p,game))
			if not Types.matches(value,str(p["value_type"])): return done("注册数据类型不符")
			registered[p["name"]] = value
			return done()
		"save_service":
			var slot: int = 0 if p["operation"] in ["quick_save","quick_load"] else int(p["slot"])
			match str(p["operation"]):
				"load","quick_load": return load_slot(slot)
				"delete": return done(str(storage.call("remove",slot)))
				"list":
					var data: Dictionary = {"slots":storage.call("slots")}
					publish(game,id,data,context)
					return done("",data)
				_: return save_slot(slot,p)
	return done("尚无此服务适配器：" + kind)


func publish(game: Node, id: String, value: Variant, context: Dictionary) -> void:
	game.get("features").get("values")[id] = value
	if not context.has("values"): context["values"] = {}
	context["values"][id] = value


func run_subgraph(game: Node, node: Dictionary, context: Dictionary) -> RefCounted:
	if subgraph_jobs.size() >= 128: return done("同时运行的参数化子图已达128项")
	var definition: Variant = node.get("_subgraph")
	if not definition is Dictionary or not definition.get("interface") is Dictionary: return done("子图未编译，请先重新编译并应用")
	var parameters: Variant = game.get("program").call("input_value",str(node["id"]),1,JSON.parse_string(str(node["params"]["arguments"])))
	if not parameters is Dictionary: return done("子图参数必须为字典")
	var arguments: Dictionary = {}
	for entry_name: String in definition["interface"]["inputs"]:
		var field: Dictionary = definition["interface"]["inputs"][entry_name]
		var value: Variant = parameters.get(entry_name,Types.from_json(str(field["json"]),str(field["type"]),game))
		if not Types.matches(value,str(field["type"])):
			if not Types.json_compatible(value,str(field["type"])): return done("子图输入类型不符："+entry_name)
			value = Types.from_json(JSON.stringify(value),str(field["type"]),game)
		if not Types.matches(value,str(field["type"])): return done("子图输入类型不符："+entry_name)
		arguments[entry_name] = value
	for entry_name: Variant in parameters:
		if not arguments.has(entry_name): return done("子图没有此输入参数："+str(entry_name))
	var scope: Node2D = Scope.new()
	scope.name = "Subgraph_" + str(node["id"]) + "_" + str(Time.get_ticks_usec())
	game.add_child(scope)
	var child_context: Dictionary = {"messages":context.get("messages",{}).duplicate(true),"values":{},"budget":context["budget"],"arguments":arguments,"ui":context.get("ui",false)}
	var execution: RefCounted = scope.call("setup",game,definition,child_context,str(node["id"])) as RefCounted
	var task: RefCounted = Task.new()
	task.get("children").append(execution)
	subgraph_jobs.append({"task":task,"game":weakref(game),"elapsed":0.0,"timeout":float(node["params"]["timeout"]),"ui":context.get("ui",false)})
	var scope_ref: WeakRef = weakref(scope)
	task.get("cleanup").append(func() -> void:
		var current: Node = scope_ref.get_ref() as Node
		if current != null: current.queue_free())
	game.get("tasks").call("when",execution,func(task_state: String,_value: Variant) -> void:
		if task.get("state") != "running": return
		if task_state != "completed": task.call("finish",task_state,null,str(execution.get("detail"))); return
		if not child_context["exit_seen"]["value"]: task.call("finish","failed",null,"子图没有到达执行出口"); return
		var returned: Dictionary = child_context["returns"]
		for entry_name: String in definition["interface"]["outputs"]:
			if not returned.has(entry_name) or not Types.matches(returned[entry_name],str(definition["interface"]["outputs"][entry_name]["type"])): task.call("finish","failed",null,"子图返回值缺失或类型不符："+entry_name); return
		publish(game,str(node["id"]),returned.duplicate(true),context)
		task.call("finish","completed",returned))
	return task


func lifecycle(operation: String) -> RefCounted:
	var game: Node = current_game()
	if operation == "quit": get_tree().quit.call_deferred(); return done()
	if operation == "menu":
		state = "menu"
		get_tree().paused = false
		owns_pause = false
		return scenes.call("request",str(manifest.get("menu_scene","")),0.25) as RefCounted
	if game == null: return done("当前没有运行中的游戏场景")
	match operation:
		"initialize": state = "initialized"
		"start": game.call("session_command",0); state = "running"
		"pause":
			if game.get("state") == "running": game.call("session_command",3)
			state = "paused"
			get_tree().paused = true
			owns_pause = true
		"resume":
			get_tree().paused = false
			owns_pause = false
			if game.get("state") == "paused": game.call("session_command",3)
			state = "running"
		"end": game.call("session_command",1); state = "ended"
		"restart": game.call("session_command",2); state = "running"
	if not (manifest.get("native_menus",false) and operation in ["end","restart"]): notify({"initialize":"initialized","start":"started","pause":"paused","resume":"resumed","end":"ended","restart":"restarted"}.get(operation,operation))
	game.call("write_debug")
	return done()


func _unhandled_input(event: InputEvent) -> void:
	if not event.is_pressed() or event is InputEventKey and event.echo: return
	var game: Node = current_game()
	if game == null or manifest.is_empty() or inputs.call("focused_text",get_viewport()) or not str(inputs.get("capturing")).is_empty(): return
	if InputMap.has_action("Pause") and event.is_action("Pause"):
		lifecycle("resume" if state == "paused" else "pause")
		get_viewport().set_input_as_handled()
	elif InputMap.has_action("QuickSave") and event.is_action("QuickSave"):
		save_slot(0)
		get_viewport().set_input_as_handled()
	elif InputMap.has_action("QuickLoad") and event.is_action("QuickLoad"):
		load_slot(0)
		get_viewport().set_input_as_handled()
	elif get_tree().paused and inputs.call("deliver",game,event): get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	var game: Node = current_game()
	if game != null and get_tree().paused: inputs.call("tick",game)
	for job: Dictionary in subgraph_jobs.duplicate():
		if job["task"].get("state") != "running": subgraph_jobs.erase(job); continue
		var owner_game: Node = job["game"].get_ref() as Node
		if owner_game == null: job["task"].call("cancel"); continue
		if owner_game.get("state") == "paused" and not job["ui"]: continue
		job["elapsed"] = float(job["elapsed"])+delta
		if float(job["elapsed"]) >= float(job["timeout"]): job["task"].call("finish","failed",null,"子图执行超时")


func apply_settings() -> String:
	var volumes: Variant = settings.get("volumes",{})
	if not volumes is Dictionary: return "音量设置格式错误"
	for channel: String in ["Master","BGM","SFX","UI"]:
		if volumes.has(channel) and not Types.matches(volumes[channel],"number"): return "音量设置需要数字"
	var resolution: Variant = settings.get("resolution",[1280,720])
	if not Types.numeric_array(resolution,2) or float(resolution[0]) < 320 or float(resolution[1]) < 240 or float(resolution[0]) > 7680 or float(resolution[1]) > 4320: return "分辨率设置无效"
	var mode: String = str(settings.get("window","windowed"))
	if not mode in ["windowed","fullscreen","borderless"]: return "窗口模式无效"
	apply_audio_settings(current_game(), volumes)
	var window: Window = get_window()
	window.mode = Window.MODE_FULLSCREEN if mode == "fullscreen" else Window.MODE_WINDOWED
	window.borderless = mode == "borderless"
	if mode != "fullscreen": window.size = Vector2i(int(resolution[0]),int(resolution[1]))
	return ""


func apply_audio_settings(game: Node, volumes: Variant) -> void:
	if game == null or not volumes is Dictionary: return
	for channel: String in ["Master","BGM","SFX","UI"]:
		if Types.matches(volumes.get(channel), "number"):
			game.call("set_volume", channel, clampf(float(volumes[channel]), -60, 6), false)


func save_settings() -> String:
	settings["bindings"] = inputs.call("snapshot")
	var error: String = str(storage.call("save_settings",settings))
	if error.is_empty(): settings_saved = true
	return error


func settings_operation(p: Dictionary, number: float) -> String:
	match str(p["operation"]):
		"volume":
			if not settings.has("volumes"): settings["volumes"] = {}
			settings["volumes"][p["channel"]] = clampf(number,-60,6)
		"resolution": settings["resolution"] = [p["width"],p["height"]]
		"window": settings["window"] = str(p["window"])
		"reset":
			inputs.call("reset")
			settings = {"volumes":{"Master":0.0,"BGM":-12.0,"SFX":-4.0,"UI":-8.0},"resolution":[1280,720],"window":"windowed"}
		"load":
			var loaded: Dictionary = storage.call("read_settings")
			if loaded.has("error"): return str(loaded["error"])
			settings = loaded
			if loaded.get("bindings") is Dictionary:
				var load_error: String = inputs.call("restore",loaded["bindings"])
				if not load_error.is_empty(): return load_error
	var error: String = apply_settings()
	if error.is_empty(): error = save_settings()
	if error.is_empty(): notify("settings_changed",settings.duplicate(true))
	return error


func save_slot(slot: int, p: Dictionary = {}) -> RefCounted:
	var game: Node = current_game()
	if game == null: return done("当前没有可保存的游戏场景")
	var scene: String = game.scene_file_path
	if scene.is_empty() and get_tree().current_scene != null: scene = get_tree().current_scene.scene_file_path
	if not scene.begins_with("res://") or not ResourceLoader.exists(scene): return done("请先将游戏保存为项目场景")
	var variables: Dictionary = game.get("variables").duplicate(true)
	var names: PackedStringArray = str(p.get("variables","")).split(",",false)
	if not names.is_empty():
		for entry_name: String in variables.keys():
			if not entry_name in names: variables.erase(entry_name)
	var actor_path: String = str(p.get("actor",manifest.get("actor","Player")))
	var actor: Node = Access.node(game,actor_path)
	var actor_data: Dictionary = {}
	if actor != null:
		for property: String in str(p.get("state_keys","position,velocity,hp,health,facing")).split(",",false):
			if Access.has_property(actor,property): actor_data[property] = Access.read(actor,property)
	var data: Dictionary = {"scene":scene,"variables":variables,"globals":globals.duplicate(true),"registered":registered.duplicate(true),"actor":{"path":actor_path,"properties":actor_data},"maps":game.get("world_tools").call("export_changes")}
	data["runtime"] = {"state":game.get("state"),"score":game.get("score"),"elapsed":game.get("elapsed"),"clock":game.get("program").get("clock"),"machines":game.get("program").get("machines").duplicate(true),"health":game.get("program").get("health").duplicate(true)}
	var encoded: Variant = Types.encode(data,game)
	var error: String = Types.encoding_error(encoded)
	if not error.is_empty(): return done(error)
	# Storage owns the encoded envelope; encode once at the scene-aware boundary.
	error = str(storage.call("save_encoded",slot,encoded))
	return done(error)


func load_slot(slot: int) -> RefCounted:
	var stored: Dictionary = storage.call("read",slot)
	if stored.has("error"): return done(str(stored["error"]))
	var data: Dictionary = stored["data"]
	var scene: String = str(data.get("scene",""))
	if not scene.begins_with("res://") or ".." in scene or not ResourceLoader.exists(scene): return done("存档场景不存在")
	for field: String in ["variables","globals","registered","actor","maps"]:
		if not data.get(field) is Dictionary: return done("存档结构缺少：" + field)
	pending_save = data.duplicate(true)
	return scenes.call("request",scene,0.2) as RefCounted


func restore_pending() -> RefCounted:
	if restore_task != null and restore_task.get("state") == "running": return restore_task
	var game: Node = current_game()
	if pending_save.is_empty(): return done()
	if game == null or not game.get("initialized"): return done("存档目标游戏尚未就绪")
	restore_task = Task.new()
	var snapshot: Dictionary = pending_save.duplicate(true)
	pending_save.clear()
	apply_save.call_deferred(restore_task,snapshot,game)
	return restore_task


func apply_save(task: RefCounted, snapshot: Dictionary, game: Node) -> void:
	game.call("session_command",0)
	await get_tree().process_frame
	if not is_instance_valid(game): task.call("finish","failed",null,"恢复时场景已退出"); return
	var data: Variant = Types.decode(snapshot,game)
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] not in ["blackboard","boolean"]: continue
		var scope: String = str(node["params"].get("scope","game"))
		var values: Dictionary = data["globals"] if scope == "project" else data["variables"]
		var entry_name: String = str(node["params"]["name"])
		if values.has(entry_name) and not Types.matches(values[entry_name],str(node["params"].get("value_type","bool"))): task.call("finish","failed",null,"存档变量类型与当前蓝图不符："+entry_name); return
	var actor: Node = Access.node(game,str(data["actor"].get("path","")))
	var properties: Variant = data["actor"].get("properties",{})
	if not properties is Dictionary: task.call("finish","failed",null,"存档角色属性格式无效"); return
	if actor == null and not properties.is_empty(): task.call("finish","failed",null,"存档角色节点不存在"); return
	for property: String in properties:
		var validation: String = Access.validate_write(actor,property,properties[property])
		if not validation.is_empty(): task.call("finish","failed",null,validation); return
	var runtime: Variant = data.get("runtime",{})
	if not runtime is Dictionary: task.call("finish","failed",null,"存档运行状态格式无效"); return
	if not runtime.is_empty():
		if not runtime.get("machines") is Dictionary or not runtime.get("health") is Dictionary or not runtime.get("state") in ["waiting","running","paused","dead"]: task.call("finish","failed",null,"存档状态结构无效"); return
		for key_name: String in ["score","elapsed","clock"]:
			if not Types.matches(runtime.get(key_name),"number") or float(runtime[key_name]) < 0: task.call("finish","failed",null,"存档计时／计分无效"); return
		for entry_name: String in runtime["machines"]:
			var declaration: Dictionary = {}
			for node: Dictionary in game.get("game_blueprint")["nodes"]:
				if node["kind"] == "fsm" and node["params"]["name"] == entry_name: declaration = node
			if declaration.is_empty() or not runtime["machines"][entry_name] is Dictionary or not runtime["machines"][entry_name].get("current") in str(declaration["params"]["states"]).split(",",false): task.call("finish","failed",null,"存档状态机与当前蓝图不符"); return
		for id: String in runtime["health"]:
			var declaration: Dictionary = Model.find(game.get("game_blueprint"),id)
			var row: Variant = runtime["health"][id]
			if declaration.get("kind") != "health" or not row is Dictionary or not Types.matches(row.get("value"),"number") or not Types.matches(row.get("immune_until"),"number") or float(row["value"]) < 0 or float(row["value"]) > float(declaration["params"]["max"]): task.call("finish","failed",null,"存档生命状态无效"); return
	var error: String = str(game.get("world_tools").call("restore_changes",data["maps"]))
	if not error.is_empty(): last_error = error; task.call("finish","failed",null,error); return
	for entry_name: String in data["variables"]:
		if game.get("variables").has(entry_name): game.get("variables")[entry_name] = data["variables"][entry_name]
	globals = data["globals"].duplicate(true)
	registered = data["registered"].duplicate(true)
	if actor != null and properties is Dictionary:
		for property: String in properties:
			var property_error: String = Access.write(actor,property,properties[property])
			if not property_error.is_empty(): last_error = property_error
	if not runtime.is_empty():
		game.set("score",int(runtime["score"]))
		game.set("elapsed",float(runtime["elapsed"]))
		game.get("program").set("clock",float(runtime["clock"]))
		for entry_name: String in runtime["machines"]: game.get("program").get("machines")[entry_name].merge({"current":runtime["machines"][entry_name]["current"],"previous":runtime["machines"][entry_name].get("previous","")},true)
		for id: String in runtime["health"]: game.get("program").get("health")[id] = runtime["health"][id].duplicate(true)
		game.get("hud").call("refresh_health")
		if runtime["state"] == "dead": game.call("session_command",1)
	state = "ended" if game.get("state") == "dead" else "running"
	notify("loaded",{"scene":game.scene_file_path})
	task.call("finish")
