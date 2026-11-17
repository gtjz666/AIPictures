@tool
extends RefCounted
## Declarative module catalog shared by the editor, builder and shipped game.
const BASE_TITLES: Dictionary = {"session": "游戏状态／计分", "input": "游戏按键", "runner": "自动奔跑角色", "world": "背景／地面滚动", "spawner": "障碍生成／碰撞", "hud": "菜单／分数／设置UI", "mixer": "音频总线混音", "screen": "画面比例", "audio": "播放声音", "timer": "计时器", "branch": "条件分支", "sequence": "顺序执行", "delay": "延迟", "boolean": "布尔变量", "custom": "自定义模块"}
const BASE_INPUTS: Dictionary = {"session": ["开始", "游戏结束", "重新开始", "暂停／继续", "加分"], "input": [], "runner": ["开始／重置", "跳跃", "死亡", "停止"], "world": ["开始／重置", "停止"], "spawner": ["开始／清空", "停止"], "hud": ["游戏画面", "结束菜单", "开始菜单", "暂停菜单", "更新分数", "开关设置"], "mixer": [], "screen": [], "audio": ["播放", "停止", "暂停", "继续"], "timer": ["启动", "停止", "重置"], "branch": ["判断", "布尔条件"], "sequence": ["执行"], "delay": ["执行"], "boolean": [], "custom": ["执行"]}
const BASE_OUTPUTS: Dictionary = {"session": ["开始时", "结束时", "重开时", "暂停时", "继续时", "分数变化"], "input": ["跳跃键", "开始键", "重开键", "暂停键"], "runner": ["起跳时", "落地时", "死亡时", "死亡动画结束", "地面脚步"], "world": [], "spawner": ["碰到角色", "越过障碍"], "hud": ["开始按钮", "重开按钮", "暂停按钮", "跳跃按钮", "按钮音效"], "mixer": [], "screen": [], "audio": ["播放结束"], "timer": ["到时"], "branch": ["成立", "不成立"], "sequence": ["先执行1", "再执行2"], "delay": ["等待后"], "boolean": ["布尔值"], "custom": ["完成", "备用"]}
const Extra: GDScript = preload("extended_registry.gd")
const Types: GDScript = preload("blueprint_types.gd")
const Registry: GDScript = preload("game_registry.gd")
const Link: GDScript = preload("resource_link.gd")
static var TITLES: Dictionary = joined(joined(BASE_TITLES, Registry.TITLES), Extra.TITLES)
static var INPUTS: Dictionary = joined(joined(BASE_INPUTS, Registry.INPUTS), Extra.INPUTS)
static var OUTPUTS: Dictionary = joined(joined(BASE_OUTPUTS, Registry.OUTPUTS), Extra.OUTPUTS)
const SINGLETONS: Array[String] = ["session", "input", "runner", "world", "spawner", "hud", "mixer", "screen"]
const HUD_TEXT: Array = [["start_text", "开始按钮文字", "text", "START"], ["retry_text", "重开按钮文字", "text", "RETRY"], ["pause_text", "暂停按钮文字", "text", "PAUSE"], ["resume_text", "继续按钮文字", "text", "RESUME"], ["over_text", "结束标题", "text", "GAME OVER"], ["jump_text", "跳跃按钮文字", "text", "JUMP"], ["audio_text", "声音设置文字", "text", "AUDIO"], ["close_text", "关闭按钮文字", "text", "CLOSE"], ["score_text", "分数标签", "text", "SCORE"], ["best_text", "最高分标签", "text", "BEST"], ["subtitle", "标题说明", "text", "Jump. Avoid. Try again."]]
# field, Chinese label, type, default, minimum/options/filter, maximum.
const FIELDS: Dictionary = {
	"session": [["points_per_second", "每秒分数", "number", 10.0, 0, 100], ["obstacle_points", "越过障碍加分", "number", 10.0, 0, 1000], ["save_key", "独立存档名称", "text", "pixel_runner"]],
	"input": [["jump", "跳跃／开始键", "key", KEY_SPACE], ["pause", "暂停键", "key", KEY_ESCAPE], ["restart", "重开键", "key", KEY_R]],
	"runner": [["frames", "角色动画资源", "asset", "", "frames"], ["walk", "行走动画名", "text", "walk_right"], ["jump", "跳跃动画名", "text", "jump_right"], ["death", "死亡动画名", "text", "death_right"], ["height", "显示高度", "number", 84.0, 16, 300], ["collision_width", "碰撞宽度", "number", 38.0, 4, 200], ["collision_height", "碰撞高度", "number", 68.0, 4, 280], ["gravity", "重力", "number", 1600.0, 300, 4000], ["jump_velocity", "起跳速度", "number", -640.0, -1500, -200], ["step_interval", "地面脚步间隔／秒", "number", 0.22, 0.08, 2]],
	"world": [["background", "背景贴图", "asset", "", "image"], ["ground", "地面贴图", "asset", "", "image"], ["sky", "背景颜色", "color", "dceef0"], ["ground_color", "地面颜色", "color", "183d45"], ["ground_ratio", "地面高度位置", "number", 0.8, 0.55, 0.9], ["parallax", "背景滚动倍率", "number", 0.15, 0, 1]],
	"spawner": [["texture", "障碍贴图", "asset", "", "image"], ["speed", "初始滚动速度", "number", 300.0, 80, 800], ["max_speed", "最高速度", "number", 500.0, 80, 1000], ["acceleration", "每秒加速", "number", 3.0, 0, 30], ["interval_min", "最短生成间隔／秒", "number", 1.5, 0.3, 8], ["interval_max", "最长生成间隔／秒", "number", 2.4, 0.3, 10], ["width", "障碍宽度", "number", 36.0, 10, 160], ["height", "障碍高度", "number", 58.0, 10, 200], ["fair_spacing", "自动限制障碍高度与间距", "bool", true]],
	"hud": [["title", "游戏标题", "text", "PIXEL RUN"], ["logo", "标题图片", "asset", "", "image"], ["panel", "面板贴图（九宫格）", "asset", "", "image"], ["button", "按钮普通贴图", "asset", "", "image"], ["hover", "按钮悬停贴图", "asset", "", "image"], ["pressed", "按钮按下贴图", "asset", "", "image"], ["touch_jump", "显示触屏跳跃按钮", "bool", true]],
	"mixer": [["Master", "总音量／dB", "number", 0.0, -60, 6], ["BGM", "背景音乐／dB", "number", -12.0, -60, 6], ["SFX", "游戏音效／dB", "number", -4.0, -60, 6], ["UI", "界面声音／dB", "number", -8.0, -60, 6]],
	"screen": [["width", "基础画面宽度", "integer", 960, 480, 3840], ["height", "基础画面高度", "integer", 540, 240, 2160], ["aspect", "画面适配", "choice", "keep", {"keep": "保持比例／黑边", "expand": "扩展可见区域"}], ["pixel", "像素最近邻显示", "bool", true]],
	"audio": [["path", "音频文件", "asset", "", "audio"], ["channel", "输出总线", "choice", "SFX", {"BGM": "背景音乐", "SFX": "游戏音效", "UI": "界面声音"}], ["loop", "循环播放", "bool", false], ["volume", "独立音量／dB", "number", 0.0, -60, 6], ["voices", "同时播放数量", "integer", 2, 1, 8], ["demo", "空文件时使用演示音色", "choice", "jump", {"none": "静音", "music": "演示配乐", "step": "演示脚步", "jump": "演示跳跃", "death": "演示死亡", "click": "演示按钮"}]],
	"timer": [["seconds", "间隔／秒", "number", 1.0, 0.01, 120], ["repeat", "重复", "bool", true]],
	"branch": [["condition", "判断条件", "choice", "running", {"running": "游戏进行中", "grounded": "角色已落地", "dead": "游戏已结束", "paused": "游戏已暂停", "score": "达到分数"}], ["threshold", "分数阈值", "number", 100.0, 0, 100000]],
	"sequence": [], "delay": [["seconds", "等待／秒", "number", 0.5, 0.01, 120]],
	"boolean": [["name", "变量名称", "text", "can_act"], ["value", "初始值", "bool", true]],
	"custom": [["script", "模块脚本", "asset", "", "script"]]}


static func joined(first: Dictionary, second: Dictionary) -> Dictionary:
	var result: Dictionary = first.duplicate(true)
	result.merge(second, true)
	return result


static func port_type(data: Dictionary, id: String, port: int, output: bool) -> int:
	var node: Dictionary = find(data, id)
	return Extra.port_type(str(node["kind"]), node["params"], port, output) if Extra.TITLES.has(node["kind"]) else Registry.port_type(str(node["kind"]), node["params"], port, output)


static func color_for(type: int) -> Color:
	return Color({9:"b6a0ee",10:"966edb",11:"ffc876",12:"73d8ce",13:"9ab767",14:"c7a775",15:"cf8fae"}[type]) if type >= 9 else Color.MEDIUM_SEA_GREEN if type == 6 else Color.SKY_BLUE if type == 7 else Color.HOT_PINK if type == 8 else Color.WHITE


static func summary(node: Dictionary) -> String:
	var p: Dictionary = node["params"]
	match str(node["kind"]):
		"key_event": return OS.get_keycode_string(int(p["key"]))
		"blackboard", "set_variable", "boolean", "fsm", "event_emit", "event_listener": return str(p["name"]).left(22)
		"set_state": return str(p["state"])
		"health": return str(p["caption"])
		"cooldown", "timer", "delay": return str(p["seconds"]) + "s"
		"audio": return str(p["demo"]) if str(p["path"]).is_empty() else str(p["path"]).get_file().left(22)
		"node_action", "signal_event": return str(p["target"]).left(22)
		"module": return str(p["path"]).get_file().left(22)
	return ""


static func scene_preset() -> Dictionary:
	var result: Dictionary = preset()
	result["template"] = "scene2d"
	result["nodes"] = result["nodes"].filter(func(node: Dictionary) -> bool: return node["kind"] in ["session", "input", "hud", "mixer", "screen"])
	result["edges"] = result["edges"].filter(func(edge: Dictionary) -> bool: return not find(result, edge["from"]).is_empty() and not find(result, edge["to"]).is_empty())
	result["edges"].append({"from": "session", "from_port": 1, "to": "hud", "to_port": 1})
	by_kind(result, "session")["params"].merge({"points_per_second": 0.0, "save_key": "scene_game"}, true)
	by_kind(result, "hud")["params"].merge({"title": "MY GAME", "subtitle": "Build. Play. Create.", "touch_jump": false}, true)
	return result


static func params(kind: String) -> Dictionary:
	var result: Dictionary = {}
	for field: Array in fields(kind):
		result[field[0]] = field[3]
	return result


static func fields(kind: String) -> Array:
	return FIELDS[kind] + HUD_TEXT if kind == "hud" else Registry.FIELDS[kind] + Registry.BUTTON_EFFECTS if kind == "button" else FIELDS[kind] if FIELDS.has(kind) else Registry.FIELDS[kind] if Registry.FIELDS.has(kind) else Extra.FIELDS[kind]


static func module(id: String, kind: String, x: float, y: float) -> Dictionary:
	return {"id": id, "kind": kind, "position": [x, y], "params": params(kind)}


static func preset() -> Dictionary:
	var nodes: Array = []
	for entry: Array in [["input", 40, 100], ["session", 370, 100], ["runner", 720, 100], ["spawner", 1080, 100], ["world", 1420, 100], ["hud", 370, 620], ["mixer", 40, 620], ["screen", 40, 1000]]:
		nodes.append(module(str(entry[0]), str(entry[0]), float(entry[1]), float(entry[2])))
	for entry: Array in [["music", "music", "BGM", true, 720, 620], ["steps", "step", "SFX", false, 1080, 620], ["jump_sfx", "jump", "SFX", false, 1420, 620], ["death_sfx", "death", "SFX", false, 1760, 620], ["click", "click", "UI", false, 1760, 950]]:
		var node: Dictionary = module(str(entry[0]), "audio", float(entry[4]), float(entry[5]))
		node["params"].merge({"demo": entry[1], "channel": entry[2], "loop": entry[3]}, true)
		nodes.append(node)
	var edges: Array = []
	for entry: Array in [["input",0,"runner",1],["input",1,"session",0],["input",2,"session",2],["input",3,"session",3],
		["session",0,"runner",0],["session",0,"world",0],["session",0,"spawner",0],["session",0,"hud",0],["session",0,"music",0],
		["session",1,"runner",2],["session",1,"world",1],["session",1,"spawner",1],["session",1,"music",1],
		["session",3,"music",2],["session",3,"hud",3],["session",4,"music",3],["session",4,"hud",0],["session",5,"hud",4],
		["runner",0,"jump_sfx",0],["runner",3,"hud",1],["runner",4,"steps",0],["runner",2,"death_sfx",0],
		["spawner",0,"session",1],["spawner",1,"session",4],["hud",0,"session",0],["hud",1,"session",2],["hud",2,"session",3],["hud",3,"runner",1],["hud",4,"click",0]]:
		edges.append({"from": entry[0], "from_port": entry[1], "to": entry[2], "to_port": entry[3]})
	edges.append({"from": "runner", "from_port": 0, "to": "steps", "to_port": 1})
	edges.append({"from": "session", "from_port": 1, "to": "steps", "to_port": 1})
	return {"version": 1, "type": "runner_game", "nodes": nodes, "edges": edges}


static func find(data: Dictionary, id: String) -> Dictionary:
	for node: Dictionary in data.get("nodes", []):
		if node["id"] == id:
			return node
	return {}


static func by_kind(data: Dictionary, kind: String) -> Dictionary:
	for node: Dictionary in data.get("nodes", []):
		if node["kind"] == kind:
			return node
	return {}


static func frames_at(path: String) -> SpriteFrames:
	if path.is_empty():
		return null
	var resource: Resource = load(path)
	if resource is SpriteFrames:
		return resource as SpriteFrames
	if resource is PackedScene:
		var state: SceneState = (resource as PackedScene).get_state()
		for index: int in range(state.get_node_count()):
			for prop: int in range(state.get_node_property_count(index)):
				if state.get_node_property_name(index, prop) == &"sprite_frames":
					return state.get_node_property_value(index, prop) as SpriteFrames
	return null


static func validate(data: Dictionary, resources: bool = false) -> String:
	data = upgrade(data)
	if data.get("version") != 1 or data.get("type") != "runner_game" or not data.get("nodes") is Array or not data.get("edges") is Array:
		return "游戏蓝图格式不正确。"
	if data["nodes"].size() > 256 or data["edges"].size() > 800:
		return "最多256个模块／800条连线（含展开子图）。"
	var ids: Dictionary = {}
	var singles: Dictionary = {}
	var variables: Dictionary = {}
	var machines: Dictionary = {}
	var bound_buttons: Dictionary = {}
	for raw: Variant in data["nodes"]:
		if not raw is Dictionary:
			return "模块格式无效。"
		var id: String = str(raw.get("id", ""))
		var kind: String = str(raw.get("kind", ""))
		if id.is_empty() or not id.is_valid_identifier() or ids.has(id) or not TITLES.has(kind) or not raw.get("params") is Dictionary or not raw.get("position") is Array or raw["position"].size() != 2:
			return "模块编号、位置或类型无效。"
		for value: Variant in raw["position"]:
			if not (value is float or value is int) or not is_finite(float(value)) or absf(float(value)) > 100000:
				return "模块位置无效。"
		ids[id] = kind
		if kind in SINGLETONS:
			if singles.has(kind):
				return TITLES[kind] + "只能放一个。"
			singles[kind] = true
		var p: Dictionary = raw["params"]
		var reference_data: Dictionary = raw.duplicate(true)
		if kind == "subgraph" and raw.get("_subgraph") is Dictionary:
			if reference_data.get("resources") is Dictionary: reference_data["resources"].erase("path")
		if resources and not Link.metadata_problem(reference_data).is_empty():
			return id + "：" + Link.metadata_problem(reference_data)
		for field: Array in fields(kind):
			if kind == "subgraph" and field[0] == "path" and raw.get("_subgraph") is Dictionary: continue
			var value: Variant = p.get(field[0])
			var type: String = str(field[2])
			if type in ["number", "integer", "key"]:
				if not (value is float or value is int) or not is_finite(float(value)):
					return str(field[1]) + "需要数字。"
				if type == "key" and (int(value) <= 0 or int(value) > 67108863 or float(value) != int(value)):
					return "键位无效。"
				if type != "key" and (float(value) < float(field[4]) or float(value) > float(field[5]) or type == "integer" and float(value) != int(value)):
					return str(field[1]) + "超出范围。"
			elif type == "bool":
				if not value is bool:
					return str(field[1]) + "需要开关值。"
			elif not value is String or str(value).length() > (16384 if type == "json" else 1024):
				return str(field[1]) + "文本无效。"
			elif type == "json" and JSON.new().parse(str(value)) != OK:
				return str(field[1]) + "需要有效JSON。"
			elif type == "node" and not str(value).is_empty() and not Types.relative_path(str(value)):
				return str(field[1]) + "需要项目内相对节点路径。"
			elif type == "choice" and not field[4].has(value):
				return str(field[1]) + "选项无效。"
			elif type == "color" and not Color.html_is_valid(str(value)):
				return "颜色无效。"
			elif type == "asset" and not str(value).is_empty():
				if not str(value).begins_with("res://") or ".." in str(value):
					return "请选择当前项目内的资源。"
				if resources:
					var resource_problem: String = Link.problem(str(value), str(field[4]))
					if not resource_problem.is_empty():
						return id + "／" + str(field[1]) + "：" + resource_problem
					if field[4] == "module":
						if not FileAccess.file_exists(str(value)):
							return "子图不存在：" + str(value)
						continue
					if not ResourceLoader.exists(str(value)):
						return "资源不存在：" + str(value)
					var resource: Resource = load(str(value))
					if field[4] == "scene" and not resource is PackedScene or field[4] == "image" and not resource is Texture2D or field[4] == "audio" and not resource is AudioStream or field[4] == "frames" and frames_at(str(value)) == null:
						return "资源类型不符：" + str(field[1])
					if field[4] == "script" and (not resource is GDScript or not (resource as GDScript).can_instantiate() or (resource as GDScript).get_instance_base_type() != &"RefCounted"):
						return "模块需为继承RefCounted的脚本。"
					if field[4] == "script":
						var found: bool = false
						for method: Dictionary in (resource as GDScript).get_script_method_list():
							if method["name"] == &"_init" and method["args"].size() > method.get("default_args", []).size():
								return "自定义模块构造函数不能要求参数。"
							if method["name"] == &"execute" and method["args"].size() == 1:
								found = true
						if not found:
							return "模块需提供execute(context)方法。"
		if kind in ["typed_value","blackboard","set_variable","module_input","module_output","event_send","data_register","property_set","ui_control"] and str(p.get("json","null")) != "null":
			var initial: Variant = JSON.parse_string(str(p["json"]))
			if initial != null and not Types.json_compatible(initial,str(p["value_type"])): return id+"：默认JSON与所选数据类型不符"
		if kind in ["session", "boolean", "blackboard"]:
			var name: String = str(p["save_key"] if kind == "session" else p["name"])
			if not name.is_valid_identifier() or variables.has(name):
				return "存档／变量名需有效且不重复。"
			variables[name] = "bool" if kind == "boolean" else str(p.get("value_type", "save"))
		if kind == "health" and float(p["initial"]) > float(p["max"]):
			return id + "：初始生命不能超过上限。"
		if kind in ["set_variable", "fsm", "set_state", "event_emit", "event_listener"] and not str(p["name"]).is_valid_identifier():
			return id + "：名称需为有效标识符。"
		if kind == "fsm":
			var states: PackedStringArray = str(p["states"]).split(",", false)
			var unique: Dictionary = {}
			for state: String in states:
				if not state.is_valid_identifier() or unique.has(state):
					return id + "：状态需使用不重复的标识符，以逗号分隔。"
				unique[state] = true
			if states.is_empty() or not str(p["initial"]) in states or machines.has(p["name"]):
				return id + "：初始状态无效或状态机重名。"
			for transition: String in str(p["transitions"]).split(";", false):
				var pair: PackedStringArray = transition.split(">")
				if pair.size() != 2 or not pair[0] in states or not pair[1] in states:
					return id + "：转换示例idle>move;move>idle，且状态必须存在。"
			machines[p["name"]] = states
		if kind in ["node_action", "signal_event"] and (str(p["target"]).is_empty() or str(p["target"]).begins_with("/") or ":" in str(p["target"]) or ".." in str(p["target"])):
			return id + "：目标需为游戏根节点下的相对路径。"
		if kind == "button" and not str(p["target"]).is_empty():
			var path: String = str(p["target"])
			if path.begins_with("/") or ":" in path or ".." in path or bound_buttons.has(path):
				return id + "：按钮目标需为唯一的项目内相对节点路径。"
			bound_buttons[path] = true
		if resources and kind in ["spawn_scene", "module"] and str(p["scene"] if kind == "spawn_scene" else p["path"]).is_empty():
			return id + "：请选择资源。"
		if kind == "spawner" and (float(p["interval_max"]) < float(p["interval_min"]) or float(p["max_speed"]) < float(p["speed"])):
			return "最大间隔／速度不能小于最小值。"
		if kind == "input" and (p["jump"] == p["pause"] or p["jump"] == p["restart"] or p["pause"] == p["restart"]):
			return "跳跃、暂停、重开请使用不同按键。"
		if resources and kind == "runner" and not str(p["frames"]).is_empty():
			var frames: SpriteFrames = frames_at(str(p["frames"]))
			for clip: String in [str(p["walk"]), str(p["jump"]), str(p["death"])]:
				if not frames.has_animation(clip) or frames.get_frame_count(clip) == 0 or frames.get_animation_speed(clip) <= 0:
					return "角色缺少动画：" + clip
		if resources and kind == "runner" and str(p["frames"]).is_empty() and (p["walk"] != "walk_right" or p["jump"] != "jump_right" or p["death"] != "death_right"):
			return "未选择角色素材时，请保留演示动画名walk_right／jump_right／death_right。"
		if resources and kind == "custom" and str(p["script"]).is_empty():
			return "请先选择或编写自定义模块脚本。"
	for kind: String in (["session", "input", "hud", "mixer", "screen"] if data.get("template", "runner") == "scene2d" else SINGLETONS):
		if not singles.has(kind):
			return "请保留核心模块：" + TITLES[kind]
	if resources:
		var runner_count: int = int(singles.has("runner")) + int(singles.has("world")) + int(singles.has("spawner"))
		if runner_count not in [0, 3]:
			return "自动奔跑角色、背景地面和跑酷障碍需同时配置；其它玩法可直接使用通用2D模板。"
	var seen: Dictionary = {}
	var boolean_inputs: Dictionary = {}
	for raw: Variant in data["edges"]:
		if not raw is Dictionary:
			return "连线格式无效。"
		var source: String = str(raw.get("from", ""))
		var dest: String = str(raw.get("to", ""))
		if not ids.has(source) or not ids.has(dest):
			return "连线引用缺失模块。"
		for field: String in ["from_port", "to_port"]:
			var value: Variant = raw.get(field, 0)
			if not (value is float or value is int) or not is_finite(float(value)) or absf(float(value)) > 1000 or float(value) != int(value):
				return "端口编号必须是整数。"
		var out_port: int = int(raw.get("from_port", 0))
		var in_port: int = int(raw.get("to_port", 0))
		if out_port < 0 or out_port >= OUTPUTS[ids[source]].size() or in_port < 0 or in_port >= INPUTS[ids[dest]].size():
			return "连线端口无效。"
		var type: int = port_type(data, source, out_port, true)
		if type != port_type(data, dest, in_port, false):
			return source + " → " + dest + "：端口类型不一致。"
		if type != 0:
			var input_key: String = dest + ":" + str(in_port)
			if boolean_inputs.has(input_key):
				return dest + "：每个数据输入只能连接一个来源。"
			boolean_inputs[input_key] = true
		if source == dest:
			return "模块不能直接连接自身；重复执行请使用计时器。"
		var key: String = source + ":" + str(out_port) + ":" + dest + ":" + str(in_port)
		if seen.has(key):
			return "连线重复。"
		seen[key] = true
	var visits: Dictionary = {}
	for id: String in ids:
		if data_cycle(data, id, visits):
			return id + "：数据计算存在循环。"
	if resources:
		for node: Dictionary in data["nodes"]:
			var p: Dictionary = node["params"]
			if node["kind"] == "set_variable" and variables.get(p["name"], "") != p["value_type"]:
				return str(node["id"]) + "：变量不存在或类型不符。"
			if node["kind"] == "set_variable":
				for declaration: Dictionary in data["nodes"]:
					if declaration["kind"] in ["blackboard","boolean"] and declaration["params"]["name"] == p["name"] and declaration["params"].get("scope","game") != p.get("scope","game"): return str(node["id"])+"：写入与变量声明作用域不一致"
			if node["kind"] == "set_state" and (not machines.has(p["name"]) or not p["state"] in machines.get(p["name"], [])):
				return str(node["id"]) + "：状态机或目标状态不存在。"
	return ""


static func data_cycle(data: Dictionary, id: String, visits: Dictionary) -> bool:
	if visits.get(id, 0) == 1:
		return true
	if visits.get(id, 0) == 2:
		return false
	visits[id] = 1
	for edge: Dictionary in data["edges"]:
		if edge["to"] == id and port_type(data, str(edge["from"]), int(edge["from_port"]), true) != 0:
			# Stateful outputs (health/FSM/variables) are storage, not recursive expressions.
			if find(data, str(edge["from"]))["kind"] in ["math", "compare", "logic", "format_text"] + Extra.PURE and data_cycle(data, str(edge["from"]), visits):
				return true
	visits[id] = 2
	return false


static func add_combo(data: Dictionary, kind: String) -> Dictionary:
	var result: Dictionary = data.duplicate(true)
	var prefix: String = "combo_" + str(Time.get_ticks_usec()) + "_"
	var definitions: Array = []
	var wires: Array = []
	if kind == "health":
		definitions = [["damage", "key_event", {"key": KEY_J}], ["heal", "key_event", {"key": KEY_K}], ["cooldown", "cooldown", {}], ["hp", "health", {}], ["format", "format_text", {"template": "HP: {value}"}], ["notice", "ui_message", {}]]
		wires = [["damage", 0, "cooldown", 0], ["cooldown", 0, "hp", 0], ["heal", 0, "hp", 1], ["hp", 0, "notice", 0], ["hp", 2, "format", 0], ["format", 0, "notice", 1]]
	elif kind == "fsm":
		definitions = [["attack_key", "key_event", {"key": KEY_F}], ["cooldown", "cooldown", {"seconds": 0.4}], ["fsm", "fsm", {"name": prefix + "states", "states": "idle,attack", "transitions": "idle>attack;attack>idle"}], ["attack", "set_state", {"name": prefix + "states", "state": "attack"}], ["wait", "delay", {"seconds": 0.4}], ["idle", "set_state", {"name": prefix + "states", "state": "idle"}], ["notice", "ui_message", {}]]
		wires = [["attack_key", 0, "cooldown", 0], ["cooldown", 0, "attack", 0], ["attack", 0, "wait", 0], ["wait", 0, "idle", 0], ["fsm", 0, "notice", 0], ["fsm", 1, "notice", 1]]
	for index: int in range(definitions.size()):
		var item: Array = definitions[index]
		var node: Dictionary = module(prefix + str(item[0]), str(item[1]), 400 + (index % 3) * 370, 1300 + floorf(float(index) / 3.0) * 320)
		node["params"].merge(item[2], true)
		result["nodes"].append(node)
	for item: Array in wires:
		result["edges"].append({"from": prefix + str(item[0]), "from_port": item[1], "to": prefix + str(item[2]), "to_port": item[3]})
	if kind == "health":
		result["edges"].append({"from": prefix + "hp", "from_port": 1, "to": by_kind(result, "session")["id"], "to_port": 1})
	return result


static func category(kind: String) -> String:
	return Extra.category(kind) if Extra.TITLES.has(kind) else Registry.category(kind)


static func upgrade(data: Dictionary) -> Dictionary:
	var result: Dictionary = data.duplicate(true)
	if not result.get("nodes") is Array: return result
	for raw: Variant in result["nodes"]:
		if not raw is Dictionary or not raw.get("params") is Dictionary: continue
		var kind: String = str(raw.get("kind", ""))
		if kind in ["blackboard", "set_variable"] and not raw["params"].has("json"): raw["params"]["json"] = "null"
		if kind in ["blackboard", "set_variable"] and not raw["params"].has("scope"): raw["params"]["scope"] = "game"
		if kind == "blackboard" and not raw["params"].has("reset_global"): raw["params"]["reset_global"] = false
		if kind == "button":
			for addition: Array in Registry.BUTTON_EFFECTS:
				if not raw["params"].has(addition[0]): raw["params"][addition[0]] = addition[3]
	return result
