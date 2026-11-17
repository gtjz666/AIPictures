@tool
extends RefCounted
## Shared value contract. JSON data never instantiates arbitrary classes.
const NAMES: Dictionary = {"bool":"布尔", "number":"数字", "text":"文字", "vector2":"Vector2", "vector3":"Vector3（数据）", "color":"颜色RGBA", "node":"节点引用", "resource":"资源引用", "array":"数组", "dictionary":"字典"}
const PORTS: Dictionary = {"bool":6, "number":7, "text":8, "vector2":9, "vector3":10, "color":11, "node":12, "resource":13, "array":14, "dictionary":15}


static func matches(value: Variant, kind: String) -> bool:
	match kind:
		"bool": return value is bool
		"number": return (value is int or value is float) and is_finite(float(value))
		"text": return value is String
		"vector2": return value is Vector2 and (value as Vector2).is_finite()
		"vector3": return value is Vector3 and (value as Vector3).is_finite()
		"color": return value is Color and is_finite(value.r) and is_finite(value.g) and is_finite(value.b) and is_finite(value.a)
		"node": return value == null or value is Node and is_instance_valid(value)
		"resource": return value == null or value is Resource
		"array": return value is Array
		"dictionary": return value is Dictionary
	return false


static func default_json(kind: String) -> String:
	return str({"bool":"false","number":"0","text":"\"\"","vector2":"[0,0]","vector3":"[0,0,0]","color":"\"ffffffff\"","node":"null","resource":"null","array":"[]","dictionary":"{}"}.get(kind,"null"))


static func default_value(kind: String) -> Variant:
	match kind:
		"bool": return false
		"number": return 0.0
		"text": return ""
		"vector2": return Vector2.ZERO
		"vector3": return Vector3.ZERO
		"color": return Color.WHITE
		"array": return []
		"dictionary": return {}
	return null


static func from_json(text: String, kind: String, root: Node = null) -> Variant:
	var value: Variant = JSON.parse_string(text)
	match kind:
		"vector2":
			if numeric_array(value, 2): return Vector2(float(value[0]), float(value[1]))
		"vector3":
			if numeric_array(value, 3): return Vector3(float(value[0]), float(value[1]), float(value[2]))
		"color":
			if value is String and Color.html_is_valid(value): return Color(value)
			if numeric_array(value, 4): return Color(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
		"node":
			if value is String and root != null and relative_path(value): return root.get_node_or_null(NodePath(value))
		"resource":
			if value is String and value.begins_with("res://") and not ".." in value and ResourceLoader.exists(value): return load(value)
		_:
			if matches(value, kind): return value
	return default_value(kind)


static func numeric_array(value: Variant, count: int) -> bool:
	return value is Array and value.size() == count and value.all(func(item: Variant) -> bool: return matches(item, "number"))


static func relative_path(path: String) -> bool:
	return not path.is_empty() and not path.begins_with("/") and not ":" in path and not ".." in path and not "\\" in path


static func initial(p: Dictionary, root: Node = null) -> Variant:
	var kind: String = str(p.get("value_type", "number"))
	return p[kind] if kind in ["bool", "number", "text"] and p.has(kind) else from_json(str(p.get("json", "null")), kind, root)


static func json_compatible(raw: Variant, kind: String) -> bool:
	if matches(raw,kind): return true
	match kind:
		"vector2": return numeric_array(raw,2)
		"vector3": return numeric_array(raw,3)
		"color": return numeric_array(raw,4) or raw is String and Color.html_is_valid(raw)
		"node": return raw is String and relative_path(raw)
		"resource": return raw is String and raw.begins_with("res://") and not ".." in raw
	return false


static func encode(value: Variant, root: Node = null, depth: int = 0) -> Variant:
	if depth > 16: return {"$invalid":"数据嵌套超过16层"}
	if value == null or value is bool or value is String: return value
	if value is int or value is float: return value if is_finite(float(value)) else {"$invalid":"非有限数字"}
	if value is Vector2: return {"$type":"vector2", "value":[value.x, value.y]}
	if value is Vector3: return {"$type":"vector3", "value":[value.x, value.y, value.z]}
	if value is Color: return {"$type":"color", "value":[value.r, value.g, value.b, value.a]}
	if value is Resource:
		var path: String = value.resource_path
		return {"$type":"resource", "value":path} if path.begins_with("res://") and ResourceLoader.exists(path) else {"$invalid":"内存资源不能直接存档"}
	if value is Node and is_instance_valid(value) and root != null and (root == value or root.is_ancestor_of(value)):
		return {"$type":"node", "value":str(root.get_path_to(value))}
	if value is Array:
		return value.map(func(item: Variant) -> Variant: return encode(item, root, depth + 1))
	if value is Dictionary:
		var row: Dictionary = {}
		for key: Variant in value:
			if not key is String or key.begins_with("$"): return {"$invalid":"字典键须为不以$开头的文字"}
			row[key] = encode(value[key], root, depth + 1)
		return row
	return {"$invalid":"不支持直接保存的运行时对象"}


static func decode(value: Variant, root: Node = null, depth: int = 0) -> Variant:
	if depth > 16: return null
	if value is Array: return value.map(func(item: Variant) -> Variant: return decode(item, root, depth + 1))
	if value is Dictionary:
		if value.has("$type"):
			return from_json(JSON.stringify(value.get("value")), str(value["$type"]), root)
		var row: Dictionary = {}
		for key: Variant in value:
			row[key] = decode(value[key], root, depth + 1)
		return row
	return value


static func encoding_error(value: Variant) -> String:
	if value is Dictionary:
		if value.has("$invalid"): return str(value["$invalid"])
		for item: Variant in value.values():
			var error: String = encoding_error(item)
			if not error.is_empty(): return error
	if value is Array:
		for item: Variant in value:
			var error: String = encoding_error(item)
			if not error.is_empty(): return error
	return ""
