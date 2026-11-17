@tool
extends RefCounted
## Exactly one terminal transition. Cancellation invokes the same cleanup path.
signal settled(state: String, value: Variant)
var state: String = "running"
var value: Variant
var detail: String = ""
var persistent: bool = false
var cleanup: Array[Callable] = []
var children: Array[RefCounted] = []


func finish(next: String = "completed", result: Variant = null, reason: String = "") -> void:
	if state != "running": return
	state = next
	value = result
	detail = reason
	for child: RefCounted in children:
		if child.get("state") == "running" and not child.get("persistent"): child.call("finish", "cancelled", null, reason)
	children.clear()
	var work: Array[Callable] = cleanup
	cleanup = []
	for callback: Callable in work:
		if callback.is_valid(): callback.call()
	settled.emit(state, value)


func cancel() -> void:
	finish("cancelled", null, "主动取消")
