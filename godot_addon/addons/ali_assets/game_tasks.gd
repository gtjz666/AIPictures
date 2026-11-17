extends Node
## Awaitable graph execution beside the legacy immediate queue.
const Task: GDScript = preload("blueprint_task.gd")
const Model: GDScript = preload("game_model.gd")
var game: Node
var roots: Dictionary = {}
var timers: Array[Dictionary] = []
var groups: Array[Dictionary] = []
var last_states: Dictionary = {}


func setup(controller: Node) -> void:
	game = controller
	process_mode = Node.PROCESS_MODE_ALWAYS


func done(state: String = "completed", value: Variant = null, reason: String = "") -> RefCounted:
	var task: RefCounted = Task.new()
	task.call("finish", state, value, reason)
	return task


func when(task: RefCounted, callback: Callable) -> void:
	if task.get("state") != "running": callback.call(str(task.get("state")), task.get("value"))
	else: task.connect("settled", callback, CONNECT_ONE_SHOT)


func launch(id: String, port: int = 0, context: Dictionary = {}) -> RefCounted:
	if roots.size() >= 128: return done("failed", null, "异步入口超过128项")
	var node: Dictionary = Model.find(game.get("game_blueprint"), id)
	if context.is_empty(): context = {"messages":game.get("program").get("messages").duplicate(true), "values":{}, "budget":{"left":512}}
	if not context.has("budget"): context["budget"] = {"left":512}
	if port > 0 and node.get("kind") in ["animation","audio_fx","camera2d","task_group","scene_service"] and port < (4 if node["kind"] in ["animation","audio_fx"] else 2):
		if node["kind"] == "task_group":
			for row: Dictionary in groups.duplicate():
				if row.get("id") == id: row["task"].call("cancel")
		else: game.get("features").call("start",node,port,context)
		if port == 1:
			if roots.has(id): roots[id].call("cancel")
			return edges(id,5 if node["kind"] == "task_group" else 1,context,[])
		return done()
	if roots.has(id) and roots[id].get("state") == "running":
		if node.get("params", {}).get("retrigger", "replace") == "ignore": return roots[id]
		roots[id].call("cancel")
	var task: RefCounted = walk(id, port, context, [])
	if task.get("state") == "running": roots[id] = task
	when(task, func(state: String, _value: Variant) -> void:
		if roots.get(id) == task: roots.erase(id)
		last_states[id] = {"state":state,"detail":str(task.get("detail"))}
		game.get("program").call("record", id, "任务：" + state + (" · " + str(task.get("detail")) if not str(task.get("detail")).is_empty() else "")))
	return task


func wait_seconds(seconds: float, ui: bool = false) -> RefCounted:
	if seconds <= 0: return done()
	if timers.size() >= 1024: return done("failed",null,"等待任务已达1024项")
	var task: RefCounted = Task.new()
	timers.append({"task":task,"remaining":seconds,"ui":ui})
	return task


func edges(source: String, port: int, context: Dictionary, stack: Array) -> RefCounted:
	if context.get("exit") is Dictionary and context["exit"].get("node") == source and int(context["exit"].get("port",-1)) == port:
		context["exit_seen"]["value"] = true
		return done()
	var factories: Array[Callable] = []
	for edge: Dictionary in game.get("game_blueprint")["edges"]:
		if edge["from"] == source and int(edge.get("from_port", 0)) == port and Model.port_type(game.get("game_blueprint"), source, port, true) == 0:
			var id: String = str(edge["to"])
			var input: int = int(edge.get("to_port", 0))
			var branch_context: Dictionary = context.duplicate(true)
			branch_context["budget"] = context["budget"]
			for shared: String in ["arguments","returns","exit_seen"]:
				if context.has(shared): branch_context[shared] = context[shared]
			factories.append(func() -> RefCounted: return walk(id, input, branch_context, stack))
	return compose(factories, false)


func walk(id: String, port: int, context: Dictionary, stack: Array) -> RefCounted:
	if stack.size() >= 64 or id in stack: return done("failed", null, "异步流程存在循环或超过64层：" + id)
	context["budget"]["left"] = int(context["budget"]["left"]) - 1
	if int(context["budget"]["left"]) < 0: return done("failed", null, "异步流程超过512步预算")
	var node: Dictionary = Model.find(game.get("game_blueprint"), id)
	if node.is_empty(): return done("failed", null, "模块不存在：" + id)
	var next_stack: Array = stack + [id]
	var kind: String = str(node["kind"])
	last_states[id] = {"state":"running","detail":"执行输入 "+str(port)}
	var p: Dictionary = node["params"]
	var operation: RefCounted
	var emissions: Array[Dictionary] = []
	var is_group: bool = kind == "task_group"
	if is_group:
		if groups.size() >= 256: return done("failed",null,"串并行任务已达256项")
		if port == 1:
			if roots.has(id): roots[id].call("cancel")
			return done()
		var factories: Array[Callable] = []
		context["ui"] = bool(context.get("ui",false)) or bool(p["ui"])
		for output: int in range(int(p["branches"])):
			factories.append(func() -> RefCounted: return edges(id, output, context, next_stack))
		operation = compose(factories, p["mode"] == "serial")
		groups.append({"id":id,"task":operation,"elapsed":0.0,"timeout":float(p["timeout"]),"ui":bool(p["ui"])})
		if not p["wait"]: operation = done()
	elif kind == "delay" or kind == "wait_task":
		operation = wait_seconds(float(p["seconds"]), bool(p.get("ui", false)) or bool(context.get("ui",false)))
	elif game.get("features").call("has_kind", kind):
		operation = game.get("features").call("start", node, port, context) as RefCounted
	else:
		emissions = game.call("capture_node", id, port, context)
		operation = done()
	var task: RefCounted = Task.new()
	task.get("children").append(operation)
	when(operation, func(state: String, value: Variant) -> void:
		last_states[id] = {"state":state,"detail":str(operation.get("detail"))}
		if task.get("state") != "running": return
		var output: int = 4 if is_group else 0
		if state != "completed": output = (5 if state == "cancelled" else 6) if is_group else (1 if state == "cancelled" else 2)
		if state == "failed": game.get("program").call("record", id, "任务失败：" + str(operation.get("detail")))
		var factories: Array[Callable] = []
		if not emissions.is_empty():
			for emitted: Dictionary in emissions:
				factories.append(func() -> RefCounted: return edges(str(emitted["id"]), int(emitted["port"]), context, next_stack))
		elif game.get("features").call("has_kind", kind) or is_group or kind in ["delay", "wait_task"]:
			factories.append(func() -> RefCounted: return edges(id, output, context, next_stack))
		var following: RefCounted = compose(factories, false)
		task.get("children").append(following)
		when(following, func(next_state: String, next_value: Variant) -> void:
			if task.get("state") != "running": return
			var final: String = next_state if next_state != "completed" else state
			task.call("finish", final, next_value if next_value != null else value, str(operation.get("detail")))))
	return task


func compose(factories: Array[Callable], serial: bool) -> RefCounted:
	var task: RefCounted = Task.new()
	if factories.is_empty():
		task.call("finish")
		return task
	if serial:
		advance(task, factories, 0)
	else:
		var remaining: Dictionary = {"count":factories.size()}
		for factory: Callable in factories:
			if task.get("state") != "running": break
			var child: RefCounted = factory.call()
			task.get("children").append(child)
			when(child, func(state: String, value: Variant) -> void:
				if task.get("state") != "running": return
				remaining["count"] = int(remaining["count"]) - 1
				if state != "completed": task.call("finish", state, value, str(child.get("detail")))
				elif int(remaining["count"]) == 0: task.call("finish", "completed", value))
	return task


func advance(task: RefCounted, factories: Array[Callable], index: int) -> void:
	if task.get("state") != "running": return
	if index >= factories.size():
		task.call("finish")
		return
	var child: RefCounted = factories[index].call()
	task.get("children").append(child)
	when(child, func(state: String, value: Variant) -> void:
		if task.get("state") != "running": return
		if state != "completed": task.call("finish", state, value, str(child.get("detail")))
		else: advance(task, factories, index + 1))


func _process(delta: float) -> void:
	for row: Dictionary in timers.duplicate():
		if row["task"].get("state") != "running": timers.erase(row); continue
		if game.get("state") == "paused" and not row["ui"]: continue
		row["remaining"] = float(row["remaining"]) - delta
		if float(row["remaining"]) <= 0: row["task"].call("finish")
	for row: Dictionary in groups.duplicate():
		if row["task"].get("state") != "running": groups.erase(row); continue
		if game.get("state") == "paused" and not row["ui"]: continue
		row["elapsed"] = float(row["elapsed"]) + delta
		if float(row["timeout"]) > 0 and float(row["elapsed"]) > float(row["timeout"]): row["task"].call("finish", "failed", null, "编排任务超时")


func cancel_all() -> void:
	for task: RefCounted in roots.values().duplicate(): task.call("cancel")
	for row: Dictionary in timers.duplicate(): row["task"].call("cancel")
	for row: Dictionary in groups.duplicate(): row["task"].call("cancel")
	roots.clear()
	timers.clear()
	groups.clear()


func _exit_tree() -> void:
	cancel_all()
