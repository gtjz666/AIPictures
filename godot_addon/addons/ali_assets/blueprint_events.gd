extends Node
## SceneTree-owned bus: copies in exported packages still share one native node.
var listeners: Array[Dictionary] = []
var pending: Array[Dictionary] = []
var dispatching: bool = false
var last_fault: String = ""


static func obtain(tree: SceneTree, script: GDScript) -> Node:
	var found: Node = tree.get_first_node_in_group("ali_blueprint_event_bus")
	if found != null: return found
	var bus: Node = script.new()
	bus.name = "AlIBlueprintEvents"
	tree.root.add_child(bus)
	bus.add_to_group("ali_blueprint_event_bus")
	return bus


func subscribe(owner_node: Node, scope: String, event: String, callback: Callable) -> void:
	listeners.append({"owner":weakref(owner_node),"scope":scope,"event":event,"callback":callback})


func unsubscribe(owner_node: Node) -> void:
	listeners = listeners.filter(func(row: Dictionary) -> bool: return row["owner"].get_ref() != null and row["owner"].get_ref() != owner_node)


func send(scope: String, event: String, payload: Variant) -> void:
	if pending.size() >= 512:
		last_fault = "事件待办超过512项"
		return
	pending.append({"scope":scope,"event":event,"payload":snapshot(payload)})
	if dispatching: return
	dispatching = true
	var budget: int = 512
	while not pending.is_empty() and budget > 0:
		var item: Dictionary = pending.pop_front()
		for row: Dictionary in listeners.duplicate():
			if row["owner"].get_ref() == null: continue
			if row["scope"] == item["scope"] and row["event"] == item["event"] and row["callback"].is_valid(): row["callback"].call(snapshot(item["payload"]))
		budget -= 1
	if not pending.is_empty():
		pending.clear()
		last_fault = "事件循环超过512步"
	dispatching = false
	prune()


func snapshot(payload: Variant) -> Variant:
	return payload.duplicate(true) if payload is Array or payload is Dictionary else payload


func prune() -> void:
	listeners = listeners.filter(func(row: Dictionary) -> bool: return row["owner"].get_ref() != null and row["callback"].is_valid())


func _process(_delta: float) -> void:
	prune()
