extends SceneTree
## Read-only catalog extraction. Does not instantiate a game or create assets.
const Game: GDScript = preload("res://addons/ali_assets/game_model.gd")
const Character: GDScript = preload("res://addons/ali_assets/blueprint_model.gd")


func _initialize() -> void:
	var modules: Array[Dictionary] = []
	for kind: String in Game.TITLES:
		var fields: Array = Game.fields(kind).duplicate(true)
		for field: Array in fields:
			if field[2] == "key":
				field[3] = OS.get_keycode_string(int(field[3]))
		var input_types: Array[String] = []
		var output_types: Array[String] = []
		var names: Dictionary = {0: "执行", 6: "布尔", 7: "数字", 8: "文字"}
		for port: int in range(Game.INPUTS[kind].size()):
			input_types.append(names[Game.Registry.port_type(kind, Game.params(kind), port, false)])
		for port: int in range(Game.OUTPUTS[kind].size()):
			output_types.append(names[Game.Registry.port_type(kind, Game.params(kind), port, true)])
		modules.append({"input_types": input_types, "output_types": output_types, "id": kind, "name": Game.TITLES[kind], "inputs": Game.INPUTS[kind], "outputs": Game.OUTPUTS[kind], "fields": fields, "core": kind in Game.SINGLETONS})
	var snapshot: Dictionary = {"game_modules": modules, "character_types": Character.KINDS, "actions": Character.ACTIONS, "conditions": Character.CONDITIONS, "events": Character.EVENTS, "character_settings": Character.empty_graph()["settings"]}
	print("BLUEPRINT_CATALOG_JSON=" + JSON.stringify(snapshot))
	quit(0)
