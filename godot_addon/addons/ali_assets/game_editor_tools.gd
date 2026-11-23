@tool
extends RefCounted
const Model: GDScript = preload("game_model.gd")
const Access: GDScript = preload("blueprint_access.gd")
const DESCRIPTIONS: Dictionary = {
	"animation":"统一属性Tween、AnimationPlayer与SpriteFrames任务。完成、取消、失败分别连线；无限循环需关闭等待。停止恢复由恢复初始开关控制。",
	"task_group":"每个分支包含下游完整流程。串行等待前一分支真正结束；并行等待全部结束。旧顺序模块保持立即依次发出信号。",
	"wait_task":"受游戏暂停控制的可取消延迟；UI开关允许暂停时继续。",
	"button":"原生Button／TextureButton的四状态、声音和五事件。动效复用通用动画；Container中通过可恢复包装保持布局。",
	"ui_control":"创建或绑定原生控件，写入指定值。值类型必须与目标属性匹配；可用数据线动态输入。",
	"ui_event":"绑定原生节点信号。最多四参数时取第一参数；无参数发出所选类型默认值。目标可为场景物体或UI。",
	"tilemap":"绑定或创建TileMapLayer。复杂地图、地形与碰撞在Godot原生编辑器配置；本模块修改格子并记录存档差量。大区域每帧批处理。",
	"camera2d":"相机移动、跟随、缩放、旋转、震动、切换与边界。有限过渡可串并行等待；持续跟随在配置完成后输出完成。",
	"scene_object":"创建图片、SpriteFrames或PackedScene；绑定现有对象可显示、变换、播放动画。删除端口只删除此模块创建的对象。",
	"background":"原生Sprite2D／Parallax2D，多层、尺寸、平铺与自动滚动。背景动画请连通用动画模块。",
	"subgraph":"带命名参数与返回字典的可等待子图，局部变量隔离。保存场景时编译冻结，源JSON可不随运行包。",
	"module_input":"定义子图命名输入与默认值；将值连到需要的数据口。",
	"module_output":"定义命名返回值并执行返回。子图到达选定执行出口后，调用节点输出返回字典。",
	"input_action":"读取Godot InputMap，输出按下、释放、按住与强度。输入框聚焦时默认屏蔽游戏输入。",
	"input_bind":"为动作绑定多个键或鼠标、捕获新键、处理冲突、恢复默认并写入独立设置文件。",
	"save_service":"多槽存取；先恢复场景，再恢复注册变量、角色属性与地图差量。槽0为快速存档，设置单独保存。",
	"frame_event":"每个普通帧或物理帧触发一次，输出本次更新经过的秒数。",
	"body_contact":"读取 CharacterBody2D 最近一次移动后的地面、墙壁或天花板接触状态。",
	"scene_service":"切换或预加载场景。叠加界面可以独立编辑，打开时可暂停当前游戏，关闭后继续原局。",
	"settings_service":"分辨率、窗口模式、四路音量和输入绑定独立持久化，不随存档回退。",
	"game_service":"初始化、开始、暂停、继续、结束、重开、返回菜单与退出。框架暂停冻结世界，UI任务可继续。",
	"event_send":"发送带类型参数的命名事件；本游戏、指定角色或框架跨场景作用域。",
	"event_receive":"订阅带参数事件；场景退出自动退订。接收类型需与发送端一致。",
	"blackboard":"声明场景／子图局部变量或框架全局变量。全局变量跨场景保留；重置开关明确控制是否重新初始化。",
	"sequence":"兼容旧图：立即依次触发两个输出，不等待下游异步任务。需要等待请使用串行／并行任务。"}


static func description(kind: String) -> String:
	return str(DESCRIPTIONS.get(kind,str(Model.TITLES[kind])+"：从执行口触发，在右侧配置参数与资源；数据口按类型连接。"))


static func field_hint(kind: String, field: Array) -> String:
	var type: String = str(field[2])
	if type == "node": return "拖入当前游戏根节点下的场景节点，或填写相对路径；不允许越出此游戏场景。"
	if type == "json": return "JSON值；向量写数组，颜色写HTML字符串，节点写相对路径，资源写res://路径。修改后点击应用JSON。"
	if type == "asset": return "拖入Godot原生资源，可预览／清空／替换；原文件不修改。"
	if type == "property": return "仅提供目标节点实际具有的白名单属性，拒绝任意对象／脚本方法。"
	if type == "input_action": return "选择已有InputMap或模板默认动作；也可输入自定义动作名。"
	if field.size() > 5: return str(field[1])+" · 范围 "+str(field[4])+" — "+str(field[5])
	return str(field[1])+" · "+description(kind)


static func visible_field(node: Dictionary, field: String) -> bool:
	var kind: String = str(node["kind"])
	var p: Dictionary = node["params"]
	if kind in ["blackboard","set_variable"]:
		if field in ["bool","number","text"]: return field == p["value_type"]
		if field == "json": return not p["value_type"] in ["bool","number","text"]
	if kind == "animation":
		var mode: String = str(p["mode"])
		if field == "factor": return mode == "scale"
		if field in ["x","y","relative"]: return mode == "position"
		if field == "color": return mode == "color"
		if field in ["from_x","from_y"]: return mode in ["scale","position"] and p["use_from"]
		if field == "from_color": return mode == "color" and p["use_from"]
		if field in ["use_from","seconds","transition","ease","pingpong"]: return not mode in ["animation","frames"]
		if field in ["animation","player","retarget","remap"]: return mode == "animation"
		if field == "frames": return mode == "frames"
		if field in ["clip","speed"]: return mode in ["animation","frames"]
	if kind == "button" and field in ["hover_scale","pressed_scale","effect_seconds","click_animation"]: return p.get("effects_enabled",false)
	if kind == "scene_service":
		if field == "scene": return p["operation"] in ["change", "preload", "open_overlay"]
		if field == "fade": return p["operation"] in ["change", "reload", "menu"]
		if field == "pause_world": return p["operation"] == "open_overlay"
	if kind == "ui_control" and field in ["name","parent","x","y","width","height"]: return p["create_type"] != "none"
	if kind == "camera2d":
		if field == "follow": return p["operation"] == "follow"
		if field == "smoothing": return p["operation"] == "follow"
		if field == "angle": return p["operation"] == "rotate"
		if field == "strength": return p["operation"] == "shake"
		if field in ["right","bottom"]: return p["operation"] == "limits"
		if field in ["x","y"]: return p["operation"] in ["move","zoom","offset","limits"]
	return true


static func event_output(kind: String, port: int) -> bool:
	return Model.port_type({"nodes":[Model.module("n",kind,0,0)]},"n",port,true) == 0 and kind in ["button","ui_event","event_receive","game_event","input_action","key_event","event_listener","signal_event","input","runner","session"]


static func copy(data: Dictionary, selected: Array[String]) -> Dictionary:
	var nodes: Array = data["nodes"].filter(func(node: Dictionary) -> bool: return str(node["id"]) in selected and not node["kind"] in Model.SINGLETONS)
	var ids: Array = nodes.map(func(node: Dictionary) -> String: return str(node["id"]))
	return {"type":"ali_game_clipboard","version":1,"nodes":nodes.duplicate(true),"edges":data["edges"].filter(func(edge: Dictionary) -> bool: return edge["from"] in ids and edge["to"] in ids).duplicate(true)}


static func paste(data: Dictionary, clipboard: Variant) -> Dictionary:
	if not clipboard is Dictionary or clipboard.get("type") != "ali_game_clipboard" or clipboard.get("version") != 1 or not clipboard.get("nodes") is Array or not clipboard.get("edges") is Array: return {"error":"剪贴板中没有AlI游戏模块"}
	if clipboard["nodes"].is_empty(): return {"error":"未复制可编辑模块；核心模块不复制"}
	var next: Dictionary = data.duplicate(true)
	var ids: Dictionary = {}
	var names: Dictionary = {}
	var prefix: String = "paste_"+str(Time.get_ticks_usec())+"_"
	for node: Variant in clipboard["nodes"]:
		if not node is Dictionary or not node.get("params") is Dictionary or not Model.TITLES.has(node.get("kind")) or node["kind"] in Model.SINGLETONS or not node.get("id") is String or ids.has(node["id"]): return {"error":"剪贴板节点格式无效"}
		ids[node["id"]] = prefix+node["id"]
		if node["kind"] in ["blackboard","boolean","fsm"]: names[node["params"].get("name","")] = prefix+str(node["params"].get("name",""))
	for original: Dictionary in clipboard["nodes"]:
		var node: Dictionary = original.duplicate(true)
		node["id"] = ids[node["id"]]
		if not node.get("position") is Array or node["position"].size() != 2: return {"error":"剪贴板位置无效"}
		node["position"] = [float(node["position"][0])+60,float(node["position"][1])+60]
		if node["kind"] in ["boolean","blackboard","set_variable","fsm","set_state"] and names.has(node["params"].get("name")): node["params"]["name"] = names[node["params"]["name"]]
		next["nodes"].append(node)
	for original: Variant in clipboard["edges"]:
		if not original is Dictionary or not ids.has(original.get("from")) or not ids.has(original.get("to")): return {"error":"剪贴板连线无效"}
		var edge: Dictionary = original.duplicate(true)
		edge["from"] = ids[edge["from"]]
		edge["to"] = ids[edge["to"]]
		next["edges"].append(edge)
	var error: String = Model.validate(next)
	return {"error":error} if not error.is_empty() else {"data":next,"selected":ids.values()}
