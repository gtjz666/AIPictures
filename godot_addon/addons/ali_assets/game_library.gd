@tool
extends RefCounted
## Expand reusable flow graphs at compile time; packaged games need no JSON files.
const Model: GDScript = preload("game_model.gd")


static func signature(data: Dictionary) -> String:
	return JSON.stringify(JSON.parse_string(JSON.stringify(data))).sha256_text()


static func read_module(path: String) -> Dictionary:
	if not path.begins_with("res://") or ".." in path or path.get_extension() != "json" or not FileAccess.file_exists(path):
		return {"error": "请选择项目内的子图JSON：" + path}
	if FileAccess.get_file_as_bytes(path).size() > 1024 * 1024:
		return {"error": "子图超过1MB。"}
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not raw is Dictionary or raw.get("type") != "flow_module" or raw.get("version") != 1 or not raw.get("nodes") is Array or not raw.get("edges") is Array or not raw.get("entry") is Dictionary or not raw.get("exit") is Dictionary:
		return {"error": "子图格式不正确：" + path}
	var test: Dictionary = Model.scene_preset()
	for node: Variant in raw["nodes"]:
		if not node is Dictionary or str(node.get("kind", "")) in Model.SINGLETONS or not node.get("id") is String or not Model.find(test, str(node["id"])).is_empty():
			return {"error": "子图含核心模块或无效编号。"}
		test["nodes"].append(node)
	test["edges"].append_array(raw["edges"])
	var error: String = Model.validate(test)
	if not error.is_empty():
		return {"error": path + "：" + error}
	for entry: Array in [["entry", false], ["exit", true]]:
		var endpoint: Dictionary = raw[entry[0]]
		var node: Dictionary = Model.find(test, str(endpoint.get("node", "")))
		var value: Variant = endpoint.get("port", -1)
		if node.is_empty() or node["kind"] in Model.SINGLETONS or not (value is int or value is float) or float(value) != int(value):
			return {"error": "子图入口／出口无效。"}
		var ports: Array = Model.OUTPUTS[node["kind"]] if entry[1] else Model.INPUTS[node["kind"]]
		if int(value) < 0 or int(value) >= ports.size() or Model.port_type(test, str(node["id"]), int(value), bool(entry[1])) != 0:
			return {"error": "子图入口／出口必须是执行端口。"}
	return {"data": raw}


static func compile(data: Dictionary) -> Dictionary:
	var error: String = Model.validate(data)
	if not error.is_empty():
		return {"error": error}
	var result: Dictionary = data.duplicate(true)
	for node: Dictionary in result["nodes"]:
		node.erase("_stack")
		node.erase("_origin")
	var calls: int = 0
	while not Model.by_kind(result, "module").is_empty():
		calls += 1
		if calls > 64:
			return {"error": "子图调用超过64次。"}
		var invocation: Dictionary = Model.by_kind(result, "module")
		var path: String = str(invocation["params"]["path"])
		var stack: Array = invocation.get("_stack", [])
		if stack.size() >= 4 or path in stack:
			return {"error": str(invocation["id"]) + "：子图递归或超过4层。"}
		var loaded: Dictionary = read_module(path)
		if loaded.has("error"):
			return loaded
		var source: Dictionary = loaded["data"]
		var prefix: String = str(invocation["id"]) + "__"
		var names: Dictionary = {}
		for node: Dictionary in source["nodes"]:
			if node["kind"] in ["boolean", "blackboard", "fsm"]:
				names[str(node["params"]["name"])] = prefix + str(node["params"]["name"])
		result["nodes"].erase(invocation)
		for original: Dictionary in source["nodes"]:
			var node: Dictionary = original.duplicate(true)
			node["id"] = prefix + str(node["id"])
			node["_origin"] = invocation.get("_origin", invocation["id"])
			node["_stack"] = stack + [path]
			if node["kind"] in ["boolean", "blackboard", "set_variable", "fsm", "set_state"] and names.has(str(node["params"]["name"])):
				node["params"]["name"] = names[str(node["params"]["name"])]
			result["nodes"].append(node)
		for edge: Dictionary in result["edges"]:
			if edge["from"] == invocation["id"]:
				edge["from"] = prefix + str(source["exit"]["node"])
				edge["from_port"] = source["exit"]["port"]
			if edge["to"] == invocation["id"]:
				edge["to"] = prefix + str(source["entry"]["node"])
				edge["to_port"] = source["entry"]["port"]
		for original: Dictionary in source["edges"]:
			var edge: Dictionary = original.duplicate(true)
			edge["from"] = prefix + str(edge["from"])
			edge["to"] = prefix + str(edge["to"])
			result["edges"].append(edge)
		if result["nodes"].size() > 256 or result["edges"].size() > 800:
			return {"error": "展开后超过256模块／800连线。"}
	error = Model.validate(result, true)
	return {"error": error} if not error.is_empty() else {"data": result, "signature": signature(data)}


static func extract(data: Dictionary, selected: Array[String]) -> Dictionary:
	var nodes: Array = []
	var edges: Array = []
	var entries: Dictionary = {}
	var exits: Dictionary = {}
	for id: String in selected:
		var node: Dictionary = Model.find(data, id)
		if node.is_empty() or node["kind"] in Model.SINGLETONS or node["kind"] in ["event_listener", "signal_event", "key_event"]:
			return {"error": "请选择逻辑／动作模块，不包含核心或独立事件源。"}
		nodes.append(node.duplicate(true))
	for edge: Dictionary in data["edges"]:
		var inside_from: bool = str(edge["from"]) in selected
		var inside_to: bool = str(edge["to"]) in selected
		if inside_from and inside_to:
			edges.append(edge.duplicate(true))
		elif inside_from != inside_to:
			if Model.port_type(data, str(edge["from"]), int(edge["from_port"]), true) != 0:
				return {"error": "数据线跨越所选范围；请把相应数据节点一起选入。"}
			var endpoint: Dictionary = {"node": edge["to"] if inside_to else edge["from"], "port": edge["to_port"] if inside_to else edge["from_port"]}
			(entries if inside_to else exits)[JSON.stringify(endpoint)] = endpoint
	if entries.size() != 1 or exits.size() != 1 or nodes.is_empty():
		return {"error": "所选子图需恰好一个外部执行入口和一个外部执行出口；请先连接示例调用再保存。"}
	return {"data": {"version": 1, "type": "flow_module", "nodes": nodes, "edges": edges, "entry": entries.values()[0], "exit": exits.values()[0]}}
