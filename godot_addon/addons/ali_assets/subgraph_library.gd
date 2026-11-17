@tool
extends RefCounted
const Model: GDScript = preload("game_model.gd")


static func read(path: String) -> Dictionary:
	if not path.begins_with("res://") or ".." in path or not FileAccess.file_exists(path): return {"error":"子图文件不存在："+path}
	if FileAccess.get_file_as_bytes(path).size() > 1024*1024: return {"error":"子图超过1MB"}
	var parser: JSON = JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK: return {"error":"子图JSON损坏"}
	var data: Variant = parser.data
	if not data is Dictionary or not data.get("nodes") is Array or not data.get("edges") is Array or not data.get("entry") is Dictionary or not data.get("exit") is Dictionary: return {"error":"子图结构无效"}
	if not (data.get("type") == "parameter_module" and data.get("version") == 2 or data.get("type") == "flow_module" and data.get("version") == 1): return {"error":"子图类型／版本无效"}
	var graph: Dictionary = Model.scene_preset()
	var parameters: Dictionary = {"inputs":{},"outputs":{}}
	for raw: Variant in data["nodes"]:
		if not raw is Dictionary or raw.get("kind") in Model.SINGLETONS or raw.get("id") in ["__param_entry","__param_exit"] or not Model.find(graph,str(raw.get("id",""))).is_empty(): return {"error":"子图含核心或保留编号"}
		if raw.get("kind") in ["key_event","event_listener","signal_event","ui_event","event_receive","game_event","input_action","button"]: return {"error":"子图使用参数和执行入口，不放独立常驻事件源／按钮"}
		graph["nodes"].append(raw)
	graph["edges"].append_array(data["edges"])
	var error: String = Model.validate(graph,true)
	if not error.is_empty(): return {"error":error}
	for node: Dictionary in data["nodes"]:
		if node["kind"] not in ["module_input","module_output"]: continue
		var p: Dictionary = node["params"]
		var section: String = "inputs" if node["kind"] == "module_input" else "outputs"
		if not str(p["name"]).is_valid_identifier() or parameters[section].has(p["name"]): return {"error":"子图参数名称无效或重复"}
		parameters[section][p["name"]] = {"type":p["value_type"],"json":p["json"]}
	for row: Array in [["entry",false],["exit",true]]:
		var endpoint: Dictionary = data[row[0]]
		var node: Dictionary = Model.find(graph,str(endpoint.get("node","")))
		if node.is_empty() or node["kind"] in Model.SINGLETONS: return {"error":"子图执行端点无效"}
		var port: int = int(endpoint.get("port",-1))
		var ports: Array = Model.OUTPUTS[node["kind"]] if row[1] else Model.INPUTS[node["kind"]]
		if port < 0 or port >= ports.size() or Model.port_type(graph,str(node["id"]),port,bool(row[1])) != 0: return {"error":"子图端点必须是执行口"}
	return {"data":data,"graph":graph,"interface":parameters}


static func extract(data: Dictionary, selected: Array[String], legacy: GDScript) -> Dictionary:
	var extracted: Dictionary = legacy.extract(data,selected)
	if extracted.has("error"): return extracted
	extracted["data"]["type"] = "parameter_module"
	extracted["data"]["version"] = 2
	return extracted
