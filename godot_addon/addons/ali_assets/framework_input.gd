extends Node
## Native InputMap; defaults never overwrite an existing project action.
signal capture_finished(action: String, error: String)
const DEFAULTS: Dictionary = {"MoveLeft":[{"key":KEY_A},{"key":KEY_LEFT}],"MoveRight":[{"key":KEY_D},{"key":KEY_RIGHT}],"MoveUp":[{"key":KEY_W},{"key":KEY_UP}],"MoveDown":[{"key":KEY_S},{"key":KEY_DOWN}],"Jump":[{"key":KEY_SPACE}],"Interact":[{"key":KEY_E}],"Attack":[{"mouse":MOUSE_BUTTON_LEFT},{"key":KEY_J}],"Run":[{"key":KEY_SHIFT}],"Pause":[{"key":KEY_ESCAPE}],"Inventory":[{"key":KEY_TAB}],"Confirm":[{"key":KEY_ENTER}],"Cancel":[{"key":KEY_ESCAPE}],"QuickSave":[{"key":KEY_F5}],"QuickLoad":[{"key":KEY_F9}]}
var defaults: Dictionary = {}
var capturing: String = ""
var capture_policy: String = "reject"
var last_error: String = ""


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for action: String in DEFAULTS:
		if not InputMap.has_action(action):
			InputMap.add_action(action)
			for row: Dictionary in DEFAULTS[action]: InputMap.action_add_event(action, event_from(row))
		defaults[action] = serialize_action(action)


func event_from(data: Dictionary) -> InputEvent:
	if data.has("key"):
		var event: InputEventKey = InputEventKey.new()
		event.physical_keycode = int(data["key"]) as Key
		event.ctrl_pressed = bool(data.get("ctrl",false))
		event.alt_pressed = bool(data.get("alt",false))
		event.shift_pressed = bool(data.get("shift",false))
		event.meta_pressed = bool(data.get("meta",false))
		return event
	if data.has("mouse"):
		var event: InputEventMouseButton = InputEventMouseButton.new()
		event.button_index = int(data["mouse"]) as MouseButton
		return event
	return null


func serialize_event(event: InputEvent) -> Dictionary:
	if event is InputEventKey: return {"key":int(event.physical_keycode if event.physical_keycode != 0 else event.keycode),"ctrl":event.ctrl_pressed,"alt":event.alt_pressed,"shift":event.shift_pressed,"meta":event.meta_pressed}
	if event is InputEventMouseButton: return {"mouse":int(event.button_index)}
	return {}


func serialize_action(action: String) -> Array:
	var events: Array = []
	for event: InputEvent in InputMap.action_get_events(action):
		var row: Dictionary = serialize_event(event)
		if not row.is_empty(): events.append(row)
	return events


func snapshot() -> Dictionary:
	var data: Dictionary = {}
	for action: String in defaults: data[action] = serialize_action(action)
	return data


func validate_bindings(rows: Variant) -> String:
	if not rows is Array or rows.size() > 8: return "每个动作最多8个键位"
	for row: Variant in rows:
		if not row is Dictionary: return "键位格式错误"
		if row.has("key"):
			if not (row["key"] is int or row["key"] is float) or int(row["key"]) <= 0 or int(row["key"]) > 67108863: return "物理键代码无效"
		elif row.has("mouse"):
			if not (row["mouse"] is int or row["mouse"] is float) or int(row["mouse"]) < 1 or int(row["mouse"]) > 9: return "鼠标键代码无效"
		else: return "支持物理键或鼠标键；手柄可在Godot原生InputMap中扩展"
	return ""


func rebind(action: String, rows: Array, policy: String = "reject", append: bool = false) -> String:
	if not action.is_valid_identifier(): return "动作名称需为有效标识符"
	var error: String = validate_bindings(rows)
	if not error.is_empty(): return error
	var conflicts: Array[Dictionary] = []
	for row: Dictionary in rows:
		var event: InputEvent = event_from(row)
		for other: String in defaults:
			if other == action: continue
			for old: InputEvent in InputMap.action_get_events(other):
				if old.is_match(event,true): conflicts.append({"action":other,"event":old})
	if policy == "reject" and not conflicts.is_empty(): return "按键已绑定：" + str(conflicts[0]["action"])
	if policy == "steal":
		for conflict: Dictionary in conflicts: InputMap.action_erase_event(str(conflict["action"]),conflict["event"])
	if not InputMap.has_action(action): InputMap.add_action(action)
	if not defaults.has(action): defaults[action] = serialize_action(action)
	if not append: InputMap.action_erase_events(action)
	for row: Dictionary in rows: InputMap.action_add_event(action,event_from(row))
	return ""


func restore(data: Dictionary) -> String:
	for action: Variant in data:
		if not action is String or not action.is_valid_identifier(): return "设置中的动作名称无效"
		var error: String = validate_bindings(data[action])
		if not error.is_empty(): return error
	for action: String in data: rebind(action,data[action],"share")
	return ""


func reset(action: String = "") -> void:
	if action.is_empty(): restore(defaults)
	elif defaults.has(action): rebind(action,defaults[action],"share")


func begin_capture(action: String, policy: String = "reject") -> void:
	capturing = action
	capture_policy = policy
	last_error = ""


func _input(event: InputEvent) -> void:
	if capturing.is_empty() or not event.is_pressed() or event is InputEventKey and event.echo: return
	var row: Dictionary = serialize_event(event)
	if row.is_empty(): return
	var action: String = capturing
	capturing = ""
	if event is InputEventKey and event.keycode == KEY_ESCAPE: last_error = "已取消改键"
	else: last_error = rebind(action,[row],capture_policy)
	get_viewport().set_input_as_handled()
	capture_finished.emit(action,last_error)


func focused_text(viewport: Viewport) -> bool:
	var focus: Control = viewport.gui_get_focus_owner()
	return focus is LineEdit or focus is TextEdit


func deliver(game: Node, event: InputEvent) -> bool:
	if not capturing.is_empty(): return true
	if event is InputEventKey and event.echo: return false
	var handled: bool = false
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] != "input_action": continue
		var p: Dictionary = node["params"]
		if p["running_only"] and game.get("state") != "running": continue
		if not p["allow_ui_focus"] and focused_text(game.get_viewport()): continue
		if InputMap.has_action(str(p["action"])) and event.is_action(str(p["action"])):
			game.call("emit_port",str(node["id"]),0 if event.is_pressed() else 1)
			handled = true
	return handled


func tick(game: Node) -> void:
	if not capturing.is_empty(): return
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] != "input_action": continue
		var p: Dictionary = node["params"]
		if p["running_only"] and game.get("state") != "running": continue
		if not p["allow_ui_focus"] and focused_text(game.get_viewport()): continue
		if InputMap.has_action(str(p["action"])) and Input.is_action_pressed(str(p["action"])): game.call("emit_port",str(node["id"]),2)
