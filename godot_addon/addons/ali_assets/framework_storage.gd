extends RefCounted
## Versioned, checksummed save slots and a separate native settings file.
const Types: GDScript = preload("blueprint_types.gd")
const VERSION: int = 1
var folder: String = ""
var last_error: String = ""


func configure(key: String) -> String:
	if not key.is_valid_identifier() or key.length() > 80: return "存档项目标识无效"
	folder = "user://ali_framework_" + key
	var error: Error = DirAccess.make_dir_recursive_absolute(folder)
	return "" if error in [OK,ERR_ALREADY_EXISTS] else "无法创建存档目录"


func slot_path(slot: int) -> String:
	return folder + "/slot_" + str(slot) + ".json" if slot >= 0 and slot <= 20 and not folder.is_empty() else ""


func checksum(data: Dictionary) -> String:
	return JSON.stringify(JSON.parse_string(JSON.stringify(data))).sha256_text()


func save(slot: int, data: Dictionary) -> String:
	var encoded: Variant = Types.encode(data)
	var error: String = Types.encoding_error(encoded)
	if not error.is_empty(): return error
	return save_encoded(slot,encoded)


func save_encoded(slot: int, encoded: Dictionary) -> String:
	var path: String = slot_path(slot)
	if path.is_empty(): return "存档槽位范围为0至20"
	var payload: Dictionary = {"version":VERSION,"saved_at":Time.get_datetime_string_from_system(true),"unix_time":Time.get_unix_time_from_system(),"data":encoded,"checksum":checksum(encoded)}
	var text: String = JSON.stringify(payload,"\t")
	if text.to_utf8_buffer().size() > 16 * 1024 * 1024: return "存档超过16MB；请减少注册数据或地图差量"
	var file: FileAccess = FileAccess.open(path + ".tmp",FileAccess.WRITE)
	if file == null: return "无法写入存档临时文件"
	file.store_string(text)
	file.flush()
	file.close()
	var backup: String = path + ".bak"
	if FileAccess.file_exists(backup) and DirAccess.remove_absolute(backup) != OK: return "无法替换旧存档备份"
	if FileAccess.file_exists(path) and DirAccess.rename_absolute(path,backup) != OK: return "无法备份旧存档"
	if DirAccess.rename_absolute(path + ".tmp",path) != OK:
		if FileAccess.file_exists(backup): DirAccess.rename_absolute(backup,path)
		return "存档提交失败，旧文件已保留"
	return ""


func read(slot: int) -> Dictionary:
	var path: String = slot_path(slot)
	if path.is_empty() or not FileAccess.file_exists(path): return {"error":"存档不存在"}
	var file: FileAccess = FileAccess.open(path,FileAccess.READ)
	if file == null: return {"error":"无法读取存档"}
	if file.get_length() > 16 * 1024 * 1024: return {"error":"存档文件超过16MB"}
	var parser: JSON = JSON.new()
	var parse_error: Error = parser.parse(file.get_as_text())
	file.close()
	var parsed: Variant = parser.data if parse_error == OK else null
	if not parsed is Dictionary: return {"error":"存档数据损坏，原文件保留，可删除或恢复.bak备份"}
	if parsed.get("version") != VERSION: return {"error":"存档版本不兼容"}
	if not parsed.get("data") is Dictionary or not parsed.get("saved_at") is String or not parsed.get("checksum") is String: return {"error":"存档结构无效"}
	if checksum(parsed["data"]) != parsed["checksum"]: return {"error":"存档校验不一致，原文件保留"}
	return {"data":parsed["data"],"saved_at":parsed["saved_at"],"unix_time":parsed.get("unix_time",0),"version":VERSION}


func remove(slot: int) -> String:
	var path: String = slot_path(slot)
	if path.is_empty(): return "无效存档槽位"
	for suffix: String in ["",".bak",".tmp"]:
		if FileAccess.file_exists(path + suffix) and DirAccess.remove_absolute(path + suffix) != OK: return "删除存档失败"
	return ""


func slots() -> Array:
	var rows: Array = []
	for slot: int in range(21):
		var stored: Dictionary = read(slot)
		rows.append({"slot":slot,"exists":FileAccess.file_exists(slot_path(slot)),"valid":not stored.has("error"),"saved_at":stored.get("saved_at",""),"error":stored.get("error","")})
	return rows


func save_settings(data: Dictionary) -> String:
	if folder.is_empty(): return "设置目录尚未配置"
	var file: ConfigFile = ConfigFile.new()
	file.set_value("ali_settings","version",1)
	file.set_value("ali_settings","data",data.duplicate(true))
	return "" if file.save(folder + "/settings.cfg") == OK else "无法保存设置"


func read_settings() -> Dictionary:
	var path: String = folder + "/settings.cfg"
	if not FileAccess.file_exists(path): return {}
	var file: ConfigFile = ConfigFile.new()
	if file.load(path) != OK or file.get_value("ali_settings","version",0) != 1: return {"error":"设置文件损坏或版本不兼容"}
	var data: Variant = file.get_value("ali_settings","data",{})
	return data if data is Dictionary else {"error":"设置格式无效"}
