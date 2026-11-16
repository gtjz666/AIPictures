@tool
extends RefCounted
## Declarative module catalog shared by the editor, builder and shipped game.
const TITLES: Dictionary = {"session": "游戏状态／计分", "input": "游戏按键", "runner": "自动奔跑角色", "world": "背景／地面滚动", "spawner": "障碍生成／碰撞", "hud": "菜单／分数／设置UI", "mixer": "音频总线混音", "screen": "画面比例", "audio": "播放声音", "timer": "计时器", "branch": "条件分支", "sequence": "顺序执行", "delay": "延迟", "boolean": "布尔变量", "custom": "自定义模块"}
const INPUTS: Dictionary = {"session": ["开始", "游戏结束", "重新开始", "暂停／继续", "加分"], "input": [], "runner": ["开始／重置", "跳跃", "死亡", "停止"], "world": ["开始／重置", "停止"], "spawner": ["开始／清空", "停止"], "hud": ["游戏画面", "结束菜单", "开始菜单", "暂停菜单", "更新分数", "开关设置"], "mixer": [], "screen": [], "audio": ["播放", "停止", "暂停", "继续"], "timer": ["启动", "停止", "重置"], "branch": ["判断", "布尔条件"], "sequence": ["执行"], "delay": ["执行"], "boolean": [], "custom": ["执行"]}
const OUTPUTS: Dictionary = {"session": ["开始时", "结束时", "重开时", "暂停时", "继续时", "分数变化"], "input": ["跳跃键", "开始键", "重开键", "暂停键"], "runner": ["起跳时", "落地时", "死亡时", "死亡动画结束", "地面脚步"], "world": [], "spawner": ["碰到角色", "越过障碍"], "hud": ["开始按钮", "重开按钮", "暂停按钮", "跳跃按钮", "按钮音效"], "mixer": [], "screen": [], "audio": ["播放结束"], "timer": ["到时"], "branch": ["成立", "不成立"], "sequence": ["先执行1", "再执行2"], "delay": ["等待后"], "boolean": ["布尔值"], "custom": ["完成", "备用"]}
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


static func params(kind: String) -> Dictionary:
	var result: Dictionary = {}
	for field: Array in fields(kind):
		result[field[0]] = field[3]
	return result


static func fields(kind: String) -> Array:
	return FIELDS[kind] + HUD_TEXT if kind == "hud" else FIELDS[kind]


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
	if data.get("version") != 1 or data.get("type") != "runner_game" or not data.get("nodes") is Array or not data.get("edges") is Array:
		return "游戏蓝图格式不正确。"
	if data["nodes"].size() > 100 or data["edges"].size() > 300:
		return "最多100个模块／300条连线。"
	var ids: Dictionary = {}
	var singles: Dictionary = {}
	var variables: Dictionary = {}
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
		for field: Array in fields(kind):
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
			elif not value is String or str(value).length() > 1024:
				return str(field[1]) + "文本无效。"
			elif type == "choice" and not field[4].has(value):
				return str(field[1]) + "选项无效。"
			elif type == "color" and not Color.html_is_valid(str(value)):
				return "颜色无效。"
			elif type == "asset" and not str(value).is_empty():
				if not str(value).begins_with("res://") or ".." in str(value):
					return "请选择当前项目内的资源。"
				if resources:
					if not ResourceLoader.exists(str(value)):
						return "资源不存在：" + str(value)
					var resource: Resource = load(str(value))
					if field[4] == "image" and not resource is Texture2D or field[4] == "audio" and not resource is AudioStream or field[4] == "frames" and frames_at(str(value)) == null:
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
		if kind in ["session", "boolean"]:
			var name: String = str(p["save_key"] if kind == "session" else p["name"])
			if not name.is_valid_identifier() or variables.has(name):
				return "存档／变量名需有效且不重复。"
			variables[name] = true
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
	for kind: String in SINGLETONS:
		if not singles.has(kind):
			return "请保留核心模块：" + TITLES[kind]
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
		if (ids[source] == "boolean") != (ids[dest] == "branch" and in_port == 1):
			return "绿色布尔输出只能连接绿色条件输入。"
		if ids[source] == "boolean":
			if boolean_inputs.has(dest):
				return "每个条件输入只能接一个布尔变量。"
			boolean_inputs[dest] = true
		if source == dest:
			return "模块不能直接连接自身；重复执行请使用计时器。"
		var key: String = source + ":" + str(out_port) + ":" + dest + ":" + str(in_port)
		if seen.has(key):
			return "连线重复。"
		seen[key] = true
	return ""
