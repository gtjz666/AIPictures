extends Node
## Native Button adapter; graph events and scoped audio stay with the game.
var game: Node
var layer: CanvasLayer
var buttons: Dictionary = {}
var voices: Dictionary = {}
var connections: Array[Dictionary] = []
var originals: Array[Dictionary] = []


static func texture(p: Dictionary, key: String) -> Texture2D:
	return load(str(p[key])) as Texture2D if not str(p.get(key, "")).is_empty() else null


static func decorate(button: BaseButton, p: Dictionary) -> void:
	var normal: Texture2D = texture(p, "normal_texture")
	for entry: Array in [["normal", "normal_texture"], ["hover", "hover_texture"], ["pressed", "pressed_texture"], ["disabled", "disabled_texture"]]:
		var image: Texture2D = texture(p, str(entry[1]))
		if image == null:
			image = normal
		if button is TextureButton:
			button.set("texture_" + str(entry[0]), image)
		elif button is Button and image != null:
			var style: StyleBoxTexture = StyleBoxTexture.new()
			style.texture = image
			button.add_theme_stylebox_override(str(entry[0]), style)
	if button is Button:
		(button as Button).text = str(p["text"])
		if button.has_theme_stylebox_override("pressed"):
			button.add_theme_stylebox_override("hover_pressed", button.get_theme_stylebox("pressed"))
	button.disabled = bool(p["disabled"])


func setup(owner_game: Node) -> void:
	game = owner_game
	process_mode = Node.PROCESS_MODE_ALWAYS
	layer = CanvasLayer.new()
	layer.layer = 3
	add_child(layer)
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] != "button":
			continue
		var id: String = str(node["id"])
		var p: Dictionary = node["params"]
		var button: BaseButton
		if str(p["target"]).is_empty():
			if p["widget"] == "texture":
				button = TextureButton.new()
			else:
				button = Button.new()
			button.name = id
			if button is TextureButton:
				(button as TextureButton).ignore_texture_size = true
				(button as TextureButton).stretch_mode = TextureButton.STRETCH_SCALE
			layer.add_child(button)
			button.position = Vector2(float(p["x"]), float(p["y"]))
			button.size = Vector2(float(p["width"]), float(p["height"]))
		else:
			button = game.get_node_or_null(NodePath(str(p["target"]))) as BaseButton
			if button == null:
				game.get("program").call("fault", id, "目标不是现有Button／TextureButton：" + str(p["target"]))
				continue
			remember(button)
		decorate(button, p)
		buttons[id] = button
		var pair: Dictionary = {}
		for channel: String in ["hover", "click"]:
			var voice: AudioStreamPlayer = AudioStreamPlayer.new()
			voice.stream = load(str(p[channel + "_sound"])) as AudioStream if not str(p[channel + "_sound"]).is_empty() else null
			voice.volume_db = float(p["volume"])
			voice.bus = str(game.get("bus_names")[p["bus"]])
			add_child(voice)
			pair[channel] = voice
		voices[id] = pair
		for entry: Array in [["pressed", 0], ["button_down", 1], ["button_up", 2], ["mouse_entered", 3], ["mouse_exited", 4]]:
			var callback: Callable = dispatch.bind(id, int(entry[1]))
			button.connect(str(entry[0]), callback)
			connections.append({"button": button, "signal": str(entry[0]), "callback": callback})


func remember(button: BaseButton) -> void:
	var row: Dictionary = {"button": button, "disabled": button.disabled, "visible": button.visible, "styles": {}, "textures": {}}
	if button is Button:
		row["text"] = (button as Button).text
		for key: String in ["normal", "hover", "pressed", "disabled", "hover_pressed"]:
			row["styles"][key] = button.get_theme_stylebox(key) if button.has_theme_stylebox_override(key) else null
	if button is TextureButton:
		for key: String in ["normal", "hover", "pressed", "disabled"]:
			row["textures"][key] = button.get("texture_" + key)
	originals.append(row)


func dispatch(id: String, port: int) -> void:
	var button: BaseButton = buttons.get(id) as BaseButton
	if not is_instance_valid(button) or button.disabled or not game.get("initialized"):
		return
	if port in [0, 3]:
		var voice: AudioStreamPlayer = voices[id]["click" if port == 0 else "hover"]
		if voice.stream != null:
			voice.play()
	game.call("emit_port", id, port)


func command(id: String, port: int) -> void:
	var button: BaseButton = buttons.get(id) as BaseButton
	if not is_instance_valid(button):
		return
	match port:
		0: button.disabled = false
		1: button.disabled = true
		2: button.show()
		3: button.hide()
		4:
			if not button.disabled:
				button.pressed.emit()


func _exit_tree() -> void:
	for row: Dictionary in connections:
		if is_instance_valid(row["button"]) and row["button"].is_connected(row["signal"], row["callback"]):
			row["button"].disconnect(row["signal"], row["callback"])
	for row: Dictionary in originals:
		var button: BaseButton = row["button"] as BaseButton
		if not is_instance_valid(button):
			continue
		button.disabled = bool(row["disabled"])
		button.visible = bool(row["visible"])
		if button is Button:
			(button as Button).text = str(row["text"])
		for key: String in row["styles"]:
			if row["styles"][key] == null:
				button.remove_theme_stylebox_override(key)
			else:
				button.add_theme_stylebox_override(key, row["styles"][key])
		for key: String in row["textures"]:
			button.set("texture_" + key, row["textures"][key])
	for pair: Dictionary in voices.values():
		for voice: AudioStreamPlayer in pair.values():
			voice.stop()
