@tool
extends RefCounted
## Declarative nodes shared by the editor, compiler and native runtime.
const VALUE_TYPES: Dictionary = {"bool": "布尔", "number": "数字", "text": "文字"}
const TITLES: Dictionary = {
	"blackboard": "黑板变量", "set_variable": "写入变量", "number": "数字常量", "text": "文字常量",
	"math": "数字运算", "compare": "数字比较", "logic": "布尔运算", "game_value": "读取游戏数据",
	"do_once": "只执行一次", "gate": "执行闸门", "flip_flop": "交替执行", "cooldown": "冷却限制",
	"fsm": "状态机", "set_state": "切换状态", "event_emit": "发送命名事件", "event_listener": "接收命名事件",
	"health": "生命值", "spawn_scene": "生成场景实例", "node_action": "场景节点操作", "signal_event": "场景信号事件",
	"log": "调试记录", "module": "可复用子图", "key_event": "自定义按键事件", "format_text": "文字格式化", "ui_message": "界面提示"}
const INPUTS: Dictionary = {
	"blackboard": [], "set_variable": ["写入", "值"], "number": [], "text": [], "math": ["A", "B"], "compare": ["A", "B"], "logic": ["A", "B"], "game_value": [],
	"do_once": ["执行", "重置"], "gate": ["执行", "打开", "关闭", "切换"], "flip_flop": ["执行", "重置"], "cooldown": ["执行", "重置"],
	"fsm": ["重置"], "set_state": ["执行"], "event_emit": ["发送", "消息"], "event_listener": [],
	"health": ["伤害", "恢复", "重置", "数量"], "spawn_scene": ["生成", "清理本模块实例", "X", "Y"], "node_action": ["执行", "X", "Y"], "signal_event": [],
	"log": ["执行", "文字"], "module": ["执行"], "key_event": [], "format_text": ["值"], "ui_message": ["显示", "文字"]}
const OUTPUTS: Dictionary = {
	"blackboard": ["当前值"], "set_variable": ["完成"], "number": ["数字"], "text": ["文字"], "math": ["结果"], "compare": ["结果"], "logic": ["结果"], "game_value": ["值"],
	"do_once": ["通过"], "gate": ["通过"], "flip_flop": ["A", "B", "本次为A"], "cooldown": ["通过", "冷却中"],
	"fsm": ["进入状态", "当前状态", "离开状态", "上一状态"], "set_state": ["成功", "拒绝"], "event_emit": ["已发送"], "event_listener": ["收到", "消息"],
	"health": ["变化", "耗尽", "当前生命", "生命比例"], "spawn_scene": ["成功", "失败"], "node_action": ["成功", "失败"], "signal_event": ["触发", "首个参数"],
	"log": ["完成"], "module": ["完成"], "key_event": ["按下", "释放"], "format_text": ["文字"], "ui_message": ["完成"]}
const FIELDS: Dictionary = {
	"blackboard": [["name", "变量名", "text", "value"], ["value_type", "类型", "choice", "number", VALUE_TYPES], ["number", "初始数字", "number", 0.0, -1000000, 1000000], ["text", "初始文字", "text", ""], ["bool", "初始布尔值", "bool", false], ["reset", "新一局恢复初始值", "bool", true]],
	"set_variable": [["name", "变量名", "text", "value"], ["value_type", "类型", "choice", "number", VALUE_TYPES], ["number", "默认数字", "number", 0.0, -1000000, 1000000], ["text", "默认文字", "text", ""], ["bool", "默认布尔值", "bool", false]],
	"number": [["value", "数字", "number", 1.0, -1000000, 1000000]], "text": [["value", "文字", "text", "Hello"]],
	"math": [["op", "计算", "choice", "add", {"add":"加", "subtract":"减", "multiply":"乘", "divide":"除", "min":"取小", "max":"取大"}], ["a", "未接线时A", "number", 0.0, -1000000, 1000000], ["b", "未接线时B", "number", 1.0, -1000000, 1000000]],
	"compare": [["op", "比较", "choice", "greater", {"greater":"大于", "less":"小于", "equal":"近似相等", "greater_equal":"大于等于", "less_equal":"小于等于"}], ["a", "未接线时A", "number", 0.0, -1000000, 1000000], ["b", "未接线时B", "number", 1.0, -1000000, 1000000]],
	"logic": [["op", "逻辑", "choice", "and", {"and":"同时成立", "or":"至少一个成立", "not":"A不成立"}], ["a", "未接线时A", "bool", false], ["b", "未接线时B", "bool", false]],
	"game_value": [["field", "数据", "choice", "score", {"score":"分数", "best":"最高分", "elapsed":"本局秒数", "current_speed":"滚动速度", "delta":"帧间隔"}]],
	"do_once": [["closed", "初始关闭", "bool", false]], "gate": [["open", "初始打开", "bool", true]], "flip_flop": [],
	"cooldown": [["seconds", "冷却秒数", "number", 0.5, 0.01, 120]],
	"fsm": [["name", "状态机名", "text", "player_state"], ["states", "状态（逗号分隔）", "text", "idle,move,attack,dead"], ["initial", "初始状态", "text", "idle"], ["transitions", "允许转换（空表示任意已知状态）", "text", ""]],
	"set_state": [["name", "状态机名", "text", "player_state"], ["state", "目标状态", "text", "move"]],
	"event_emit": [["name", "事件名", "text", "collected"], ["text", "消息", "text", ""]], "event_listener": [["name", "事件名", "text", "collected"]],
	"health": [["max", "生命上限", "number", 100.0, 1, 1000000], ["initial", "初始生命", "number", 100.0, 0, 1000000], ["amount", "默认伤害／恢复量", "number", 10.0, 0, 1000000], ["invulnerability", "受伤保护秒数", "number", 0.3, 0, 60], ["show", "在界面显示", "bool", true], ["caption", "界面标题", "text", "HP"]],
	"spawn_scene": [["scene", "场景文件", "asset", "", "scene"], ["name", "实例名称", "text", "Entity"], ["x", "X", "number", 200.0, -100000, 100000], ["y", "Y", "number", 200.0, -100000, 100000], ["limit", "最多存活实例", "integer", 16, 1, 64]],
	"node_action": [["target", "目标路径（相对游戏根节点）", "text", "Entity"], ["op", "操作", "choice", "show", {"show":"显示", "hide":"隐藏", "enable":"启用处理", "disable":"禁用处理", "free":"删除", "position":"设置位置", "translate":"移动距离", "velocity":"设置角色速度", "animation":"播放动画"}], ["x", "X", "number", 0.0, -100000, 100000], ["y", "Y", "number", 0.0, -100000, 100000], ["clip", "动画名", "text", "idle"]],
	"signal_event": [["target", "目标路径（相对游戏根节点）", "text", "Entity"], ["signal", "信号名", "text", "tree_exiting"]],
	"log": [["text", "文字", "text", "Blueprint event"]], "module": [["path", "子图文件", "asset", "", "module"]],
	"key_event": [["key", "按键", "key", KEY_J], ["running_only", "仅在游戏进行时触发", "bool", true]],
	"format_text": [["value_type", "输入类型", "choice", "number", VALUE_TYPES], ["template", "文字（{value}为值）", "text", "Value: {value}"]],
	"ui_message": [["text", "显示文字", "text", "Complete"], ["seconds", "显示秒数", "number", 2.0, 0.1, 60]]}
const PURE: Array[String] = ["blackboard", "number", "text", "math", "compare", "logic", "game_value", "format_text", "boolean"]


static func value_type(p: Dictionary) -> int:
	return 6 if p.get("value_type") == "bool" else 8 if p.get("value_type") == "text" else 7


static func port_type(kind: String, p: Dictionary, port: int, output: bool) -> int:
	if output:
		if kind == "boolean" or kind in ["compare", "logic"] or kind == "flip_flop" and port == 2:
			return 6
		if kind == "blackboard":
			return value_type(p)
		if kind in ["number", "math", "game_value"] or kind == "health" and port >= 2:
			return 7
		if kind in ["text", "format_text"] or kind == "fsm" and port in [1, 3] or kind in ["event_listener", "signal_event"] and port == 1:
			return 8
	else:
		if kind == "branch" and port == 1 or kind == "logic":
			return 6
		if kind == "set_variable" and port == 1 or kind == "format_text":
			return value_type(p)
		if kind in ["math", "compare"] or kind == "health" and port == 3 or kind in ["spawn_scene", "node_action"] and port >= (2 if kind == "spawn_scene" else 1):
			return 7
		if kind in ["event_emit", "log", "ui_message"] and port == 1:
			return 8
	return 0


static func category(kind: String) -> String:
	if kind in ["blackboard", "set_variable", "number", "text", "math", "compare", "logic", "game_value", "format_text", "boolean"]:
		return "变量与数据"
	if kind in ["branch", "sequence", "delay", "timer", "do_once", "gate", "flip_flop", "cooldown", "fsm", "set_state", "module"]:
		return "逻辑与状态"
	if kind in ["event_emit", "event_listener", "key_event", "signal_event", "input"]:
		return "事件与输入"
	if kind in ["spawn_scene", "node_action", "health", "custom", "log"]:
		return "场景与玩法"
	return "游戏与界面"
