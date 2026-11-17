extends RefCounted
## Narrow native property/method adapter. No arbitrary script or engine calls.
const Types: GDScript = preload("blueprint_types.gd")
const PROPERTIES: Array[String] = ["hp", "health", "facing", "dead", "visible", "position", "global_position", "scale", "rotation", "rotation_degrees", "modulate", "self_modulate", "z_index", "size", "custom_minimum_size", "pivot_offset", "text", "bbcode_enabled", "texture", "mouse_filter", "disabled", "editable", "button_pressed", "value", "min_value", "max_value", "step", "tooltip_text", "zoom", "offset", "enabled", "limit_left", "limit_top", "limit_right", "limit_bottom", "position_smoothing_enabled", "position_smoothing_speed", "scroll_offset", "autoscroll", "repeat_size", "repeat_times", "volume_db", "pitch_scale", "speed_scale", "velocity", "collision_layer", "collision_mask", "tile_set", "sprite_frames", "animation", "frame"]
const METHODS: Dictionary = {"show":0,"hide":0,"grab_focus":0,"release_focus":0,"make_current":0,"force_update_scroll":0,"reset_smoothing":0,"clear":0,"select_all":0,"set_pressed_no_signal":1,"set_value_no_signal":1}


static func node(root: Node, object_ref: Variant) -> Node:
	if "binding_root" in root and is_instance_valid(root.get("binding_root")): root = root.get("binding_root") as Node
	if object_ref is Node:
		return object_ref if is_instance_valid(object_ref) and (object_ref == root or root.is_ancestor_of(object_ref)) else null
	return root.get_node_or_null(NodePath(str(object_ref))) if Types.relative_path(str(object_ref)) else null


static func has_property(target: Object, property: String) -> bool:
	if not is_instance_valid(target) or not property.get_slice(":", 0) in PROPERTIES: return false
	var parts: PackedStringArray = property.split(":")
	if parts.size() > 2 or parts.size() == 2 and not parts[1] in ["x","y","z","r","g","b","a"]: return false
	for row: Dictionary in target.get_property_list():
		if str(row["name"]) != parts[0]: continue
		if parts.size() == 1: return true
		var current: Variant = target.get(parts[0])
		return current is Vector2 and parts[1] in ["x","y"] or current is Vector3 and parts[1] in ["x","y","z"] or current is Color and parts[1] in ["r","g","b","a"]
	return false


static func read(target: Object, property: String) -> Variant:
	target = motion_proxy(target,property)
	return target.get_indexed(NodePath(property)) if has_property(target, property) else null


static func write(target: Object, property: String, value: Variant) -> String:
	target = motion_proxy(target,property)
	var error: String = validate_write(target,property,value)
	if not error.is_empty(): return error
	var current: Variant = target.get_indexed(NodePath(property))
	if current is float and (value is int or value is float): value = float(value)
	if current is int and (value is int or value is float): value = int(value)
	target.set_indexed(NodePath(property), value)
	return ""


static func validate_write(target: Object, property: String, value: Variant) -> String:
	target = motion_proxy(target,property)
	if not has_property(target, property): return "属性不在支持范围或目标无此属性：" + property
	var current: Variant = target.get_indexed(NodePath(property))
	if current is float and (value is int or value is float): value = float(value)
	if current is int and (value is int or value is float): value = int(value)
	if current != null and typeof(current) != typeof(value): return "属性值类型不符：" + property
	if value is Resource:
		for row: Dictionary in target.get_property_list():
			if str(row["name"]) == property:
				var expected: String = str(row.get("class_name",row.get("hint_string","")))
				if expected.is_empty(): expected = str(row.get("hint_string",""))
				if ClassDB.class_exists(expected) and not value.is_class(expected): return "需要资源类型："+expected
	if value is float and not is_finite(value): return "属性需要有限数字"
	if value is Vector2 and not value.is_finite() or value is Vector3 and not value.is_finite(): return "属性需要有限向量"
	return ""


static func motion_proxy(target: Object, property: String) -> Object:
	if is_instance_valid(target) and property.get_slice(":",0) in ["position","scale","rotation","rotation_degrees"] and target.has_meta("ali_motion_wrapper"):
		var object_ref: WeakRef = target.get_meta("ali_motion_wrapper") as WeakRef
		if object_ref != null and object_ref.get_ref() != null: return object_ref.get_ref()
	return target


static func invoke(target: Node, method: String, args: Array) -> String:
	if not is_instance_valid(target) or not METHODS.has(method) or not target.has_method(method): return "不支持此方法：" + method
	if args.size() != int(METHODS[method]): return "方法参数数量不符"
	if method == "set_pressed_no_signal" and not args[0] is bool: return "需要布尔值"
	if method == "set_value_no_signal" and not Types.matches(args[0], "number"): return "需要数字"
	target.callv(method, args)
	return ""
