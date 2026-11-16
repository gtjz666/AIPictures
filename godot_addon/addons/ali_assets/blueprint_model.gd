@tool
extends RefCounted
## Data only: the graph never evaluates expressions or executes user scripts.

const ACTIONS: Dictionary = {
	"move_left": "左移", "move_right": "右移", "move_up": "上移", "move_down": "下移",
	"idle": "待机", "walk": "行走", "run": "奔跑", "jump": "跳跃", "attack": "攻击",
	"hurt": "受击", "death": "死亡", "dash": "冲刺", "roll": "翻滚", "block": "防御",
	"cast": "施法", "interact": "交互", "climb": "攀爬", "fall": "下落", "land": "落地"}
const KINDS: Array[String] = ["key", "action", "animation", "sound", "event", "branch", "sequence", "delay", "boolean", "custom"]
const FLOW: Array[String] = ["event", "branch", "sequence", "delay", "custom"]
const CONDITIONS: Dictionary = {"grounded": "已落地", "in_air": "在空中", "moving": "正在移动", "running": "正在奔跑", "always": "始终成立"}
const EVENTS: Dictionary = {"ready": "角色就绪", "hurt": "受到伤害", "death": "角色死亡", "land": "落地时", "animation_finished": "动画播放结束"}


static func empty_graph(mode: String = "two_way") -> Dictionary:
	return {"version": 1, "nodes": [], "edges": [], "settings": {
		"mode": mode, "speed": 180.0, "run_multiplier": 1.8, "gravity": 980.0, "jump_velocity": -380.0}}


static func make_node(id: String, kind: String, x: float, y: float, params: Dictionary) -> Dictionary:
	return {"id": id, "kind": kind, "position": [x, y], "params": params}


static func find_node(data: Dictionary, id: String) -> Dictionary:
	for node: Dictionary in data.get("nodes", []):
		if str(node.get("id", "")) == id:
			return node
	return {}


static func outgoing(data: Dictionary, id: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for edge: Dictionary in data.get("edges", []):
		if str(edge.get("from", "")) == id:
			result.append(find_node(data, str(edge.get("to", ""))))
	return result


static func validate(data: Dictionary, frames: SpriteFrames = null) -> String:
	if data.get("version") != 1 or not data.get("nodes") is Array or not data.get("edges") is Array or not data.get("settings") is Dictionary:
		return "蓝图文件格式不正确。"
	if data["nodes"].size() > 200 or data["edges"].size() > 400:
		return "蓝图最多200个模块、400条连线。"
	var settings: Dictionary = data["settings"]
	if str(settings.get("mode", "")) not in ["two_way", "four_way", "platformer"]:
		return "请选择双向、四向或平台角色。"
	for field: String in ["speed", "run_multiplier", "gravity", "jump_velocity"]:
		var number: Variant = settings.get(field)
		if not (number is float or number is int) or not is_finite(float(number)):
			return "运动参数需要有效数字。"
	if float(settings["speed"]) <= 0 or float(settings["speed"]) > 2000 or float(settings["run_multiplier"]) < 1 or float(settings["run_multiplier"]) > 5 or float(settings["gravity"]) < 0 or float(settings["gravity"]) > 10000 or float(settings["jump_velocity"]) >= 0 or float(settings["jump_velocity"]) < -3000:
		return "运动参数超出范围。"
	var ids: Dictionary = {}
	var actions: Dictionary = {}
	var variable_names: Dictionary = {}
	for raw: Variant in data["nodes"]:
		if not raw is Dictionary:
			return "模块格式不正确。"
		var node: Dictionary = raw
		var id: String = str(node.get("id", ""))
		var kind: String = str(node.get("kind", ""))
		if id.is_empty() or not id.is_valid_identifier() or id.length() > 80 or ids.has(id) or kind not in KINDS or not node.get("params") is Dictionary:
			return "模块名称、类型或参数无效。"
		ids[id] = kind
		var position: Variant = node.get("position")
		if not position is Array or position.size() != 2:
			return "模块位置无效。"
		for number: Variant in position:
			if not (number is float or number is int) or not is_finite(float(number)) or absf(float(number)) > 100000:
				return "模块位置超出范围。"
		var params: Dictionary = node["params"]
		if kind == "key":
			var code: Variant = params.get("code")
			if not (code is float or code is int) or float(code) != int(code) or int(code) <= 0 or int(code) > 67108864:
				return "请选择有效按键。"
		elif kind == "action":
			var action: String = str(params.get("action", ""))
			if not ACTIONS.has(action) or actions.has(action):
				return "动作类型无效或重复；多个按键可连到同一个动作模块。"
			actions[action] = true
		elif kind == "animation":
			if not params.get("clip") is String or str(params["clip"]).is_empty() or str(params["clip"]).length() > 128:
				return "请填写动画名称。"
		elif kind == "event":
			if not EVENTS.has(str(params.get("event", ""))):
				return "事件类型无效。"
		elif kind == "branch":
			if not CONDITIONS.has(str(params.get("condition", ""))) or not params.get("invert") is bool:
				return "条件分支参数无效。"
		elif kind == "delay":
			var seconds: Variant = params.get("seconds")
			if not (seconds is float or seconds is int) or not is_finite(float(seconds)) or float(seconds) < 0.01 or float(seconds) > 60:
				return "延迟范围为0.01–60秒。"
		elif kind == "boolean":
			if not params.get("value") is bool or not params.get("name") is String or not str(params["name"]).is_valid_identifier():
				return "布尔变量需填写有效名称与初始值。"
			if variable_names.has(params["name"]):
				return "布尔变量名称重复。"
			variable_names[params["name"]] = true
		elif kind == "custom":
			var path: String = str(params.get("script", ""))
			if not path.is_empty() and (not path.begins_with("res://") or ".." in path or path.get_extension() != "gd"):
				return "自定义模块需选择当前项目内的GDScript。"
		elif kind == "sound":
			var sound: Dictionary = params
			if not sound.get("path") is String:
				return "音效路径格式不正确。"
			var path: String = str(sound.get("path", ""))
			if not path.is_empty() and (not path.begins_with("res://") or ".." in path or path.get_extension().to_lower() not in ["wav", "ogg", "mp3"]):
				return "音效需为当前项目中的WAV、OGG或MP3文件。"
			if str(sound.get("trigger", "")) not in ["start", "frame", "repeat"]:
				return "音效触发方式无效。"
			for field: String in ["frame", "interval", "volume"]:
				var number: Variant = sound.get(field)
				if not (number is float or number is int) or not is_finite(float(number)):
					return "音效参数需要有效数字。"
			if float(sound["frame"]) < 0 or float(sound["frame"]) > 100000 or float(sound["frame"]) != int(sound["frame"]) or float(sound["interval"]) < 0.05 or float(sound["interval"]) > 60 or float(sound["volume"]) < -60 or float(sound["volume"]) > 6:
				return "音效参数超出范围。"
	var seen: Dictionary = {}
	var animation_outputs: Dictionary = {}
	var inputs: Dictionary = {}
	var indegree: Dictionary = {}
	var adjacency: Dictionary = {}
	for id: String in ids:
		indegree[id] = 0
		adjacency[id] = []
	for raw: Variant in data["edges"]:
		if not raw is Dictionary:
			return "连线格式不正确。"
		var source: String = str(raw.get("from", ""))
		var target: String = str(raw.get("to", ""))
		var from_port: int = int(raw.get("from_port", 0))
		var to_port: int = int(raw.get("to_port", 0))
		if not (raw.get("from_port", 0) is int or raw.get("from_port", 0) is float) or not (raw.get("to_port", 0) is int or raw.get("to_port", 0) is float) or float(raw.get("from_port", 0)) != from_port or float(raw.get("to_port", 0)) != to_port:
			return "端口编号必须是整数。"
		var pair: String = source + ":" + str(from_port) + ":" + target + ":" + str(to_port)
		if not ids.has(source) or not ids.has(target) or seen.has(pair):
			return "连线引用了不存在的模块或重复连线。"
		seen[pair] = true
		var source_kind: String = str(ids[source])
		var target_kind: String = str(ids[target])
		var boolean_edge: bool = source_kind == "boolean" and target_kind == "branch" and from_port == 0 and to_port == 1
		var valid_flow: bool = to_port == 0 and from_port >= 0 and from_port <= (1 if source_kind in ["key", "branch", "sequence", "custom"] else 0) and (
			(source_kind == "key" and (target_kind == "action" or target_kind in FLOW and target_kind != "event")) or
			(source_kind in FLOW and (target_kind in ["action", "animation", "sound"] or target_kind in FLOW and target_kind != "event")) or
			(source_kind == "action" and target_kind == "animation") or
			(source_kind == "animation" and (target_kind == "sound" or target_kind in FLOW and target_kind != "event")))
		if not boolean_edge and not valid_flow:
			return "白色端口连接执行流程；绿色布尔值只能连接条件输入。"
		if boolean_edge:
			if inputs.has(target):
				return "一个条件输入只能接一个布尔变量。"
			inputs[target] = true
		indegree[target] += 1
		adjacency[source].append(target)
		if ids[source] == "action":
			if animation_outputs.has(source):
				return "一个动作只能连接一个动画模块。"
			animation_outputs[source] = true
		if frames != null and ids[target] == "animation":
			var clip: String = str(find_node(data, target)["params"].get("clip", ""))
			if not frames.has_animation(clip) or frames.get_frame_count(clip) == 0:
				return "角色缺少动画：" + clip
		if frames != null and ids[target] == "sound":
			var sound: Dictionary = find_node(data, target)["params"]
			var path: String = str(sound.get("path", ""))
			if path.is_empty() or not ResourceLoader.exists(path) or not load(path) is AudioStream:
				return "请为已连接的音效选择项目内音频。"
			if ids[source] != "animation" and sound["trigger"] != "start":
				return "指定帧与重复音效需要直接连接动画模块。"
			var clip: String = str(find_node(data, source)["params"].get("clip", ""))
			if sound["trigger"] == "frame" and (not frames.has_animation(clip) or int(sound["frame"]) >= frames.get_frame_count(clip)):
				return "音效触发帧超出动画范围（帧号从0开始）。"
	# Acyclic execution graphs cannot hang the game in an unbounded loop.
	var ready: Array[String] = []
	for id: String in indegree:
		if indegree[id] == 0:
			ready.append(id)
	var visited: int = 0
	while not ready.is_empty():
		var id: String = ready.pop_back()
		visited += 1
		for dest: String in adjacency[id]:
			indegree[dest] -= 1
			if indegree[dest] == 0:
				ready.append(dest)
	if visited != ids.size():
		return "检测到循环连线；请使用按键、事件或重复音效触发下一次执行。"
	if frames != null:
		for node: Dictionary in data["nodes"]:
			if node["kind"] == "custom":
				var path: String = str(node["params"].get("script", ""))
				if path.is_empty() or not ResourceLoader.exists(path):
					return "请先为自定义模块选择脚本。"
				var script: GDScript = load(path) as GDScript
				if script == null or not script.can_instantiate() or script.get_instance_base_type() != &"RefCounted":
					return "自定义模块必须是可运行的RefCounted脚本。"
				var found: bool = false
				for method: Dictionary in script.get_script_method_list():
					if method["name"] == &"_init" and method["args"].size() > method.get("default_args", []).size():
						return "自定义模块的构造函数不能要求额外参数。"
					if method["name"] == &"execute" and method["args"].size() == 1:
						found = true
				if not found:
					return "自定义模块需提供execute(context)方法。"
	return ""


static func preset(mode: String, frames: SpriteFrames = null, keys: Dictionary = {}) -> Dictionary:
	var data: Dictionary = empty_graph(mode)
	var actions: Array[String] = ["move_left", "move_right", "run", "jump", "attack", "idle", "hurt", "death"]
	if mode == "four_way":
		actions.insert(2, "move_up")
		actions.insert(3, "move_down")
	var defaults: Dictionary = {"move_left": KEY_A, "move_right": KEY_D, "move_up": KEY_W, "move_down": KEY_S, "run": KEY_SHIFT, "jump": KEY_SPACE, "attack": KEY_J}
	for i: int in range(actions.size()):
		var action: String = actions[i]
		var y: float = 100 + i * 220.0
		var aid: String = "action_" + action
		data["nodes"].append(make_node(aid, "action", 380, y, {"action": action}))
		if defaults.has(action):
			var kid: String = "key_" + action
			data["nodes"].append(make_node(kid, "key", 60, y, {"code": keys.get(action, defaults[action])}))
			data["edges"].append({"from": kid, "to": aid})
		var base: String = "walk" if action.begins_with("move_") else action
		var direction: String = action.trim_prefix("move_") if mode == "four_way" and action.begins_with("move_") else "right"
		var clip: String = base + "_" + direction
		if frames != null and not frames.has_animation(clip):
			clip = base
		if frames == null or frames.has_animation(clip):
			var anim: String = "anim_" + action
			data["nodes"].append(make_node(anim, "animation", 720, y, {"clip": clip}))
			data["edges"].append({"from": aid, "to": anim})
	return data
