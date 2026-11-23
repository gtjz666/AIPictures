@tool
extends RefCounted
const Types: GDScript = preload("blueprint_types.gd")
const TERMINALS: Array[String] = ["完成", "取消", "失败"]
const TARGET: Array = ["target","目标节点","node",""]
const VALUE: Array = ["value_type","数据类型","choice","text",Types.NAMES]
const JSON_VALUE: Array = ["json","默认值JSON（向量用数组、节点用路径）","json","null"]
const TITLES: Dictionary = {"animation":"通用动画", "task_group":"串行／并行任务", "wait_task":"可等待延迟", "ui_control":"通用UI操作", "ui_event":"UI事件", "node_ref":"获取节点引用", "property_get":"读取属性", "property_set":"修改属性", "method_call":"受支持方法", "resource_ref":"获取资源引用", "typed_value":"类型化常量", "collection":"数组／字典操作", "event_send":"发送参数事件", "event_receive":"接收参数事件", "module_input":"子图输入参数", "module_output":"子图返回参数", "subgraph":"参数化子图", "camera2d":"Camera2D控制", "background":"背景／视差", "tilemap":"TileMapLayer地图", "scene_object":"场景物体", "input_action":"InputMap动作", "input_bind":"运行时改键", "audio_fx":"音频渐变／位置声音", "game_service":"游戏生命周期", "scene_service":"场景切换／转场", "settings_service":"设置管理", "save_service":"存档管理", "data_register":"注册存档数据", "game_event":"游戏／场景事件", "frame_event":"帧更新事件", "body_contact":"2D接触状态"}
const INPUTS: Dictionary = {
	"animation":["播放","停止","暂停","恢复"], "task_group":["执行","取消"], "wait_task":["等待"],
	"ui_control":["执行","值","目标"], "ui_event":[], "node_ref":[], "property_get":["目标"], "property_set":["执行","值","目标"], "method_call":["执行","参数数组","目标"], "resource_ref":[], "typed_value":[], "collection":["集合","值"],
	"event_send":["发送","参数"], "event_receive":[], "module_input":[], "module_output":["返回","值"], "subgraph":["执行","参数字典"],
	"camera2d":["执行","取消"], "background":["创建／更新","显示","隐藏","删除"], "tilemap":["执行","坐标"], "scene_object":["创建／更新","显示","隐藏","删除","播放动画"],
	"input_action":[], "input_bind":["执行"], "audio_fx":["播放","停止","暂停","恢复","淡入","淡出"], "game_service":["执行"], "scene_service":["执行","取消"], "settings_service":["执行","值"], "save_service":["执行"], "data_register":["注册／更新","数据"], "game_event":[], "frame_event":[], "body_contact":["物体"]}
const OUTPUTS: Dictionary = {
	"animation":TERMINALS, "task_group":["分支1","分支2","分支3","分支4","全部完成","取消","失败"], "wait_task":TERMINALS,
	"ui_control":TERMINALS, "ui_event":["触发","参数"], "node_ref":["节点"], "property_get":["值"], "property_set":TERMINALS, "method_call":TERMINALS, "resource_ref":["资源"], "typed_value":["值"], "collection":["结果"],
	"event_send":TERMINALS, "event_receive":["收到","参数"], "module_input":["值"], "module_output":TERMINALS, "subgraph":["完成","取消","失败","返回字典"],
	"camera2d":TERMINALS, "background":["完成","取消","失败","对象"], "tilemap":["完成","取消","失败","格子数据"], "scene_object":["完成","取消","失败","对象"], "input_action":["按下","释放","按住","强度"], "input_bind":TERMINALS, "audio_fx":TERMINALS, "game_service":TERMINALS, "scene_service":TERMINALS, "settings_service":["完成","取消","失败","当前值"], "save_service":["完成","取消","失败","槽位信息"], "data_register":TERMINALS, "game_event":["发生","参数"], "frame_event":["更新","帧间隔"], "body_contact":["是否接触"]}
const FIELDS: Dictionary = {
	"animation":[TARGET,["mode","动画类型","choice","scale",{"scale":"缩放（放大／缩小）","position":"位置","color":"RGBA","animation":"Animation／AnimationPlayer","frames":"SpriteFrames"}],["factor","目标缩放倍率","number",1.2,0.001,100],["x","目标X／相对位移X","number",0.0,-100000,100000],["y","目标Y／相对位移Y","number",-30.0,-100000,100000],["relative","位置使用相对位移","bool",true],["color","目标RGBA","color","ffffff00"],["use_from","使用指定起点","bool",false],["from_x","起点X／缩放X","number",1.0,-100000,100000],["from_y","起点Y／缩放Y","number",1.0,-100000,100000],["from_color","起点RGBA","color","ffffffff"],["seconds","持续秒数","number",0.3,0.001,120],["delay","开始延迟","number",0.0,0,120],["transition","Transition","choice","sine",{"linear":"Linear","sine":"Sine","quad":"Quad","cubic":"Cubic","back":"Back","bounce":"Bounce","elastic":"Elastic"}],["ease","Ease","choice","in_out",{"in":"In","out":"Out","in_out":"InOut","out_in":"OutIn"}],["loops","循环次数（0无限）","integer",1,0,1000],["reverse","反向播放","bool",false],["pingpong","属性动画往返","bool",false],["restore","结束／取消恢复初始","bool",false],["wait","等待结束","bool",true],["ui","暂停时继续（UI）","bool",false],["policy","属性冲突","choice","replace",{"replace":"取消旧动画并替换","reject":"拒绝新动画"}],["animation","Animation／Library资源","asset","","animation_source"],["player","已有Player相对子路径","text","AnimationPlayer"],["frames","SpriteFrames资源","asset","","frames"],["clip","片段名称（空则首个）","text",""],["speed","播放速度","number",1.0,0.01,100],["retarget","所有轨道绑定到目标本身","bool",false],["remap","轨道节点重映射JSON","json","{}"],["timeout","等待超时／秒","number",120.0,0.01,3600]],
	"task_group":[["mode","编排","choice","serial",{"serial":"串行：等待前一分支","parallel":"并行：等待全部分支"}],["branches","使用分支数","integer",2,1,4],["wait","等待全部结束","bool",true],["ui","暂停时继续（UI）","bool",false],["timeout","超时／秒","number",120.0,0.01,3600],["retrigger","重复触发","choice","replace",{"replace":"取消旧任务并重启","ignore":"忽略重复触发"}]],
	"wait_task":[["seconds","等待秒数","number",0.3,0,3600],["ui","暂停时继续（UI）","bool",false]],
	"ui_control":[TARGET,["create_type","目标留空时创建","choice","none",{"none":"仅绑定已有控件","Button":"Button","TextureButton":"TextureButton","Label":"Label","RichTextLabel":"RichTextLabel","TextureRect":"TextureRect","Panel":"Panel","PanelContainer":"PanelContainer","ProgressBar":"ProgressBar","HSlider":"Slider","CheckBox":"CheckBox","LineEdit":"LineEdit","Control":"Control"}],["name","新控件名","text","Element"],["parent","父节点（可选Container）","node",""],["x","新建X","number",40.0,-10000,10000],["y","新建Y","number",40.0,-10000,10000],["width","新建宽度","number",200.0,1,4096],["height","新建高度","number",48.0,1,4096],["operation","UI操作","choice","show",{"show":"显示","hide":"隐藏","text":"文字","texture":"图片","color":"RGBA","alpha":"透明度","size":"尺寸","position":"位置","value":"数值","value_quiet":"设置数值（无通知）","disabled":"禁用状态","editable":"可编辑状态","focus":"获取焦点"}],VALUE,JSON_VALUE],
	"ui_event":[TARGET,["signal","原生信号","text","pressed"],VALUE,["ui","游戏暂停时触发","bool",true]],
	"node_ref":[TARGET], "property_get":[TARGET,["property","支持的属性","property","position"],VALUE], "property_set":[TARGET,["property","支持的属性","property","position"],VALUE,JSON_VALUE],
	"method_call":[TARGET,["method","受支持方法","choice","show",{"show":"show","hide":"hide","grab_focus":"grab_focus","release_focus":"release_focus","make_current":"make_current","reset_smoothing":"reset_smoothing","clear":"clear","select_all":"select_all","set_pressed_no_signal":"set_pressed_no_signal","set_value_no_signal":"set_value_no_signal","move_and_slide":"move_and_slide（角色移动并滑动）"}],["arguments","参数JSON数组","json","[]"]],
	"resource_ref":[["resource","资源","asset","","resource"]], "typed_value":[VALUE,JSON_VALUE],
	"collection":[["operation","集合操作","choice","get",{"get":"按键／下标读取","set":"写入副本","append":"追加到副本","erase":"从副本删除","size":"元素数量"}],["container","集合类型","choice","dictionary",{"array":"Array","dictionary":"Dictionary"}],["key","字典键／数组下标","text","0"],VALUE,["json","默认集合JSON","json","{}"]],
	"event_send":[["name","事件名","text","event"],["scope","作用域","choice","game",{"game":"本游戏实例","project":"本游戏框架跨场景","role":"指定角色"}],TARGET,VALUE,JSON_VALUE],
	"event_receive":[["name","事件名","text","event"],["scope","作用域","choice","game",{"game":"本游戏实例","project":"本游戏框架跨场景","role":"指定角色"}],TARGET,VALUE],
	"module_input":[["name","输入参数名","text","value"],VALUE,JSON_VALUE], "module_output":[["name","返回参数名","text","result"],VALUE,JSON_VALUE], "subgraph":[["path","参数化子图文件","asset","","module"],["arguments","默认参数JSON字典","json","{}"],["timeout","等待超时／秒","number",120.0,0.01,3600]],
	"camera2d":[TARGET,["operation","相机操作","choice","move",{"move":"平滑移动","follow":"跟随目标","zoom":"缩放","rotate":"旋转","shake":"震动","current":"切换为当前","offset":"视角偏移","limits":"设置边界","stop_follow":"停止跟随"}],["follow","跟随目标","node",""],["x","X／缩放X／边界左","number",0.0,-100000,100000],["y","Y／缩放Y／边界上","number",0.0,-100000,100000],["right","边界右","number",10000.0,-100000,100000],["bottom","边界下","number",10000.0,-100000,100000],["angle","旋转度数","number",0.0,-3600,3600],["strength","震动幅度","number",8.0,0,1000],["seconds","过渡秒数","number",0.4,0.001,120],["smoothing","跟随平滑速度","number",6.0,0,100],["ui","暂停时继续","bool",false]],
	"background":[TARGET,["image","背景图片","asset","","image"],["name","新建名称","text","Background"],["x","X","number",0.0,-100000,100000],["y","Y","number",0.0,-100000,100000],["width","显示宽度（0原尺寸）","number",0.0,0,100000],["height","显示高度（0原尺寸）","number",0.0,0,100000],["rotation","旋转角度","number",0.0,-3600,3600],["alpha","透明度","number",1.0,0,1],["layer","显示层级","integer",-10,-4096,4096],["repeat_x","平铺宽度（0关闭）","number",0.0,0,100000],["repeat_y","平铺高度","number",0.0,0,100000],["parallax","使用Parallax2D","bool",false],["scroll_x","自动滚动X","number",0.0,-10000,10000],["scroll_y","自动滚动Y","number",0.0,-10000,10000],["ratio_x","视差倍率X","number",0.5,-10,10],["ratio_y","视差倍率Y","number",0.5,-10,10]],
	"tilemap":[TARGET,["tileset","TileSet资源","asset","","tileset"],["name","新建图层名","text","Ground"],["operation","地图操作","choice","bind",{"bind":"创建／绑定","set":"放置／替换","erase":"删除格子","fill":"填充矩形","clear_region":"清除矩形","read":"读取格子","world_to_cell":"世界坐标转格子","cell_to_world":"格子转世界","terrain":"地形自动连接","enabled":"图层启停","clear":"清空图层"}],["x","格子／坐标X","integer",0,-100000,100000],["y","格子／坐标Y","integer",0,-100000,100000],["width","区域宽度","integer",1,1,512],["height","区域高度","integer",1,1,512],["source","瓦片源ID","integer",0,0,100000],["atlas_x","图集X","integer",0,0,100000],["atlas_y","图集Y","integer",0,0,100000],["alternative","替代瓦片ID","integer",0,0,100000],["terrain_set","地形集合ID","integer",0,0,1000],["terrain","地形ID","integer",0,0,1000],["layer","绘制层级","integer",0,-4096,4096],["enabled","图层启用","bool",true],["collision","启用TileSet碰撞","bool",true],["save_key","地图存档标识","text","ground"]],
	"scene_object":[TARGET,["kind","资源类型","choice","image",{"image":"图片Sprite2D","frames":"SpriteFrames","scene":"PackedScene"}],["resource","资源","asset","","resource"],["name","新对象名","text","Entity"],["x","X","number",0.0,-100000,100000],["y","Y","number",0.0,-100000,100000],["scale_x","缩放X","number",1.0,-100,100],["scale_y","缩放Y","number",1.0,-100,100],["rotation","旋转度数","number",0.0,-3600,3600],["layer","显示层级","integer",0,-4096,4096],["collision","矩形碰撞","bool",false],["width","碰撞宽度","number",32.0,1,4096],["height","碰撞高度","number",32.0,1,4096],["clip","动画名","text","default"]],
	"input_action":[["action","InputMap动作","input_action","Jump"],["running_only","仅游戏进行时","bool",true],["allow_ui_focus","输入控件聚焦时仍触发","bool",false]],
	"input_bind":[["action","动作名称","input_action","Jump"],["operation","操作","choice","bind",{"bind":"替换绑定","add":"追加绑定","reset":"恢复默认","save":"保存键位","capture":"运行时捕获下一次输入"}],["bindings","绑定JSON数组","json","[{\"key\":32}]"],["conflict","冲突策略","choice","reject",{"reject":"拒绝冲突","share":"允许共享","steal":"从其它动作移除"}]],
	"audio_fx":[["path","音频资源","asset","","audio"],["channel","输出总线","choice","SFX",{"Master":"总线","BGM":"背景音乐","SFX":"游戏音效","UI":"界面声音"}],["volume","目标音量dB","number",0.0,-80,6],["seconds","渐变秒数","number",0.3,0.001,120],["loop","循环","bool",false],["spatial","位置音效","bool",false],["x","位置X","number",0.0,-100000,100000],["y","位置Y","number",0.0,-100000,100000],["wait","等待播放完成","bool",false],["persist_ui","跨场景保留界面短音","bool",false],["timeout","超时／秒","number",120.0,0.01,3600]],
	"game_service":[["operation","生命周期","choice","start",{"initialize":"初始化","start":"开始","pause":"暂停","resume":"恢复","end":"结束","restart":"重新开始","menu":"返回主菜单","quit":"退出游戏"}]],
	"scene_service":[["operation","场景操作","choice","change",{"change":"切换","reload":"重载","preload":"预加载","menu":"返回主菜单","open_overlay":"打开叠加界面","close_overlay":"关闭当前叠加界面"}],["scene","目标场景","asset","","scene"],["fade","转场淡出／淡入秒数","number",0.3,0,10],["pause_world","界面打开时暂停游戏","bool",false]],
	"settings_service":[["operation","设置操作","choice","volume",{"volume":"音量","read":"读取当前设置","reset_audio":"恢复默认音量","resolution":"分辨率","window":"窗口模式","save":"保存设置","load":"恢复已存设置","reset":"恢复全部默认"}],["channel","音量通道","choice","Master",{"Master":"Master","BGM":"BGM","SFX":"SFX","UI":"UI"}],["number","默认数值／音量dB","number",0.0,-80,6],["width","窗口宽","integer",1280,320,7680],["height","窗口高","integer",720,240,4320],["window","窗口模式","choice","windowed",{"windowed":"窗口","fullscreen":"全屏","borderless":"无边框"}]],
	"save_service":[["operation","存档操作","choice","save",{"save":"创建／覆盖","load":"读取","delete":"删除","list":"槽位列表","quick_save":"快速保存","quick_load":"快速读取","autosave":"自动保存"}],["slot","槽位（0快速）","integer",1,0,20],["variables","保存变量名（空为全部）","text",""],["actor","角色节点","node",""],["state_keys","角色属性（逗号分隔）","text","position,velocity"]],
	"data_register":[["name","注册数据名","text","quest"],["value_type","数据类型","choice","dictionary",Types.NAMES],["json","默认数据JSON","json","{}"]],
	"game_event":[["event","生命周期事件","choice","initialized",{"initialized":"初始化完成","started":"开始","paused":"暂停","resumed":"恢复","ended":"结束","restarted":"重开","scene_entered":"场景进入","scene_exiting":"场景退出","loaded":"存档恢复完成","settings_changed":"设置改变"}],["value_type","参数类型","choice","dictionary",Types.NAMES]],
	"frame_event":[["clock","更新时机","choice","physics",{"physics":"物理帧","render":"普通帧"}]],
	"body_contact":[TARGET,["surface","接触方向","choice","floor",{"floor":"地面","wall":"墙壁","ceiling":"天花板"}]]}
const PURE: Array[String] = ["node_ref","property_get","resource_ref","typed_value","collection","module_input","body_contact"]


static func port_type(kind: String, p: Dictionary, port: int, output: bool) -> int:
	if output:
		if kind == "frame_event" and port == 1: return 7
		if kind == "body_contact": return 6
		if kind in ["node_ref"] or kind in ["background","scene_object"] and port == 3: return 12
		if kind == "resource_ref": return 13
		if kind == "property_get" or kind in ["typed_value","module_input"] or kind in ["ui_event","event_receive","game_event"] and port == 1: return int(Types.PORTS.get(p.get("value_type", "text"), 8))
		if kind == "collection": return 7 if p["operation"] == "size" else int(Types.PORTS.get(p["value_type"], 8)) if p["operation"] == "get" else int(Types.PORTS[p["container"]])
		if kind in ["tilemap","subgraph","save_service","settings_service"] and port == 3: return 15
		if kind == "input_action" and port == 3: return 7
	else:
		if kind in ["property_get","body_contact"]: return 12
		if kind in ["ui_control","property_set","method_call"] and port == 2: return 12
		if kind in ["ui_control","property_set","event_send","module_output","data_register"] and port == 1: return int(Types.PORTS.get(p.get("value_type", "text"), 8))
		if kind == "method_call" and port == 1: return 14
		if kind == "subgraph" and port == 1: return 15
		if kind == "settings_service" and port == 1: return 7
		if kind == "tilemap" and port == 1: return 9
		if kind == "collection": return int(Types.PORTS[p["container"]]) if port == 0 else int(Types.PORTS.get(p["value_type"], 8))
	return 0


static func category(kind: String) -> String:
	if kind in ["animation","task_group","wait_task","subgraph"]: return "动画与异步"
	if kind in ["ui_control","ui_event"]: return "通用UI"
	if kind in ["background","tilemap","scene_object","camera2d"]: return "地图与场景"
	if kind in ["input_action","input_bind","event_send","event_receive","game_event","frame_event"]: return "事件与输入"
	if kind in ["game_service","scene_service","settings_service","save_service","data_register","audio_fx"]: return "游戏服务"
	return "变量与数据"
