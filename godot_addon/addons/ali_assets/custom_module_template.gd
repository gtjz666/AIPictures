extends RefCounted
## AlI自定义模块。只在游戏运行、执行线到达时调用，不在编辑器内执行。
## 可把本脚本复制后编写成冷却、计分、装备判断、特效等项目模块。
## context.actor: CharacterBody2D角色；context.delta: 本帧秒数。
## context.variables: 蓝图布尔变量字典，与绿色变量模块相通。
## 返回output=0走“完成”端口，output=1走“备用”端口。
## 模块应快速返回。异步等待请使用画布上的延迟节点。

func execute(context: Dictionary) -> Dictionary:
	var actor: CharacterBody2D = context.get("actor") as CharacterBody2D
	if actor == null:
		return {"output": 1}
	# 示例：context["variables"]["can_attack"] = true
	# 在这里编写你的游戏逻辑。保持接口不变，即可重复使用此模块。
	return {"output": 0}
