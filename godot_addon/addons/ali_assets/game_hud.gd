extends CanvasLayer
## Container-based HUD, adapted from the skill's signal-driven HUD pattern.
var game: Node2D
var params: Dictionary
var score_label: Label
var overlay: CenterContainer
var panel: PanelContainer
var title: Label
var subtitle: Label
var primary: Button
var settings_panel: PanelContainer
var sliders: Dictionary = {}
var health_rows: Dictionary = {}
var notifications: Label
var message_remaining: float = 0.0
var display_mode: String = "title"


func setup(controller: Node2D, settings: Dictionary) -> void:
	game = controller
	params = settings
	layer = 10
	var root: Control = Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	var theme: Theme = Theme.new()
	theme.default_font_size = 20
	theme.set_color("font_color", "Label", Color("193d45"))
	root.theme = theme
	var margin: MarginContainer = MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 24)
	margin.add_theme_constant_override("margin_right", 24)
	margin.add_theme_constant_override("margin_top", 20)
	margin.add_theme_constant_override("margin_bottom", 16)
	margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(margin)
	var spine: VBoxContainer = VBoxContainer.new()
	spine.mouse_filter = Control.MOUSE_FILTER_IGNORE
	margin.add_child(spine)
	var bar: GridContainer = GridContainer.new()
	bar.columns = 1 if int(game.get("base_size").x) < 700 else 3
	spine.add_child(bar)
	score_label = Label.new()
	score_label.add_theme_font_size_override("font_size", 16)
	score_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.add_child(score_label)
	bar.add_child(button(str(params["pause_text"]), func() -> void: game.call("event", "hud", 2), Vector2(100, 40)))
	bar.add_child(button(str(params["audio_text"]), func() -> void: settings_panel.visible = not settings_panel.visible, Vector2(100, 40)))
	var health_box: VBoxContainer = VBoxContainer.new()
	health_box.name = "HealthBars"
	spine.add_child(health_box)
	for node: Dictionary in game.get("game_blueprint")["nodes"]:
		if node["kind"] == "health" and node["params"]["show"]:
			var row: HBoxContainer = HBoxContainer.new()
			var label: Label = Label.new()
			label.text = str(node["params"]["caption"])
			row.add_child(label)
			var progress: ProgressBar = ProgressBar.new()
			progress.max_value = float(node["params"]["max"])
			progress.value = float(node["params"]["initial"])
			progress.custom_minimum_size = Vector2(180, 22)
			progress.show_percentage = false
			row.add_child(progress)
			health_box.add_child(row)
			health_rows[node["id"]] = progress
	notifications = Label.new()
	notifications.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	spine.add_child(notifications)
	var fill: Control = Control.new()
	fill.size_flags_vertical = Control.SIZE_EXPAND_FILL
	fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	spine.add_child(fill)
	var footer: HBoxContainer = HBoxContainer.new()
	spine.add_child(footer)
	var hint: Label = Label.new()
	var bindings: Dictionary = game.call("settings", "input")
	hint.text = "%s JUMP / %s PAUSE / %s RESTART" % [OS.get_keycode_string(int(bindings["jump"])), OS.get_keycode_string(int(bindings["pause"])), OS.get_keycode_string(int(bindings["restart"]))]
	if game.get("game_blueprint").get("template") == "scene2d":
		hint.text = hint.text.replace("JUMP", "START")
	hint.visible = int(game.get("base_size").x) >= 700
	hint.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hint.add_theme_font_size_override("font_size", 14)
	footer.add_child(hint)
	if params["touch_jump"]:
		footer.add_child(button(str(params["jump_text"]), func() -> void: game.call("event", "hud", 3), Vector2(120, 46)))
	overlay = CenterContainer.new()
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(overlay)
	panel = PanelContainer.new()
	panel.custom_minimum_size = Vector2(330, 0)
	panel.add_theme_stylebox_override("panel", panel_style())
	overlay.add_child(panel)
	var content: VBoxContainer = VBoxContainer.new()
	content.add_theme_constant_override("separation", 16)
	panel.add_child(content)
	if not str(params["logo"]).is_empty():
		var logo: TextureRect = TextureRect.new()
		logo.texture = load(str(params["logo"])) as Texture2D
		logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		logo.custom_minimum_size = Vector2(220, 80)
		content.add_child(logo)
	title = Label.new()
	title.text = str(params["title"])
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 32)
	content.add_child(title)
	subtitle = Label.new()
	subtitle.text = str(params["subtitle"])
	subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	subtitle.add_theme_font_size_override("font_size", 16)
	content.add_child(subtitle)
	primary = button(str(params["start_text"]), activate_primary)
	content.add_child(primary)
	content.add_child(button(str(params["audio_text"]), func() -> void: settings_panel.visible = not settings_panel.visible))
	build_settings(root)
	update_score()


func panel_style() -> StyleBox:
	if not str(params["panel"]).is_empty():
		return texture_style(str(params["panel"]))
	var style: StyleBoxFlat = StyleBoxFlat.new()
	style.bg_color = Color("f6fcf5")
	style.border_color = Color("32666a")
	style.set_border_width_all(3)
	style.set_content_margin_all(24)
	style.set_corner_radius_all(6)
	return style


func texture_style(path: String) -> StyleBoxTexture:
	var style: StyleBoxTexture = StyleBoxTexture.new()
	style.texture = load(path) as Texture2D
	for side: int in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]:
		style.set_texture_margin(side, 8)
		style.set_content_margin(side, 12)
	return style


func button(text: String, callback: Callable, minimum: Vector2 = Vector2(220, 48)) -> Button:
	var result: Button = Button.new()
	result.text = text
	result.custom_minimum_size = minimum
	result.focus_mode = Control.FOCUS_NONE
	for entry: Array in [["normal", "button", "367b79"], ["hover", "hover", "479c90"], ["pressed", "pressed", "24525e"]]:
		var path: String = str(params[str(entry[1])])
		if path.is_empty() and not str(params["button"]).is_empty():
			path = str(params["button"])
		if not path.is_empty():
			result.add_theme_stylebox_override(str(entry[0]), texture_style(path))
		else:
			var style: StyleBoxFlat = StyleBoxFlat.new()
			style.bg_color = Color(str(entry[2]))
			style.set_corner_radius_all(4)
			style.set_content_margin_all(10)
			result.add_theme_stylebox_override(str(entry[0]), style)
	result.pressed.connect(func() -> void:
		game.call("event", "hud", 4)
		callback.call())
	return result


func build_settings(root: Control) -> void:
	var center: CenterContainer = CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(center)
	settings_panel = PanelContainer.new()
	settings_panel.custom_minimum_size = Vector2(360, 0)
	settings_panel.add_theme_stylebox_override("panel", panel_style())
	settings_panel.visible = false
	center.add_child(settings_panel)
	var content: VBoxContainer = VBoxContainer.new()
	content.add_theme_constant_override("separation", 12)
	settings_panel.add_child(content)
	var label: Label = Label.new()
	label.text = str(params["audio_text"])
	content.add_child(label)
	for channel: String in ["Master", "BGM", "SFX", "UI"]:
		var caption: Label = Label.new()
		caption.text = channel
		content.add_child(caption)
		var slider: HSlider = HSlider.new()
		slider.min_value = -60
		slider.max_value = 6
		slider.step = 1
		slider.value = float(game.get("mixer_values")[channel])
		slider.custom_minimum_size = Vector2(280, 24)
		slider.focus_mode = Control.FOCUS_NONE
		slider.value_changed.connect(func(value: float) -> void: game.call("set_volume", channel, value))
		content.add_child(slider)
		sliders[channel] = slider
	content.add_child(button(str(params["close_text"]), func() -> void: settings_panel.hide()))


func activate_primary() -> void:
	game.call("event", "hud", 0 if display_mode == "title" else 1 if display_mode == "over" else 2)


func update_score() -> void:
	score_label.text = "%s %05d    %s %05d" % [str(params["score_text"]), int(game.get("score")), str(params["best_text"]), maxi(int(game.get("best")), int(game.get("score")))]


func command(port: int) -> void:
	match port:
		0:
			overlay.hide()
			settings_panel.hide()
		1:
			display_mode = "over"
			title.text = str(params["over_text"])
			subtitle.text = "%s %d / %s %d" % [str(params["score_text"]), int(game.get("score")), str(params["best_text"]), int(game.get("best"))]
			primary.text = str(params["retry_text"])
			overlay.show()
		2:
			display_mode = "title"
			title.text = str(params["title"])
			primary.text = str(params["start_text"])
			overlay.show()
		3:
			display_mode = "pause"
			title.text = str(params["pause_text"])
			primary.text = str(params["resume_text"])
			overlay.show()
		4: update_score()
		5: settings_panel.visible = not settings_panel.visible


func refresh_health() -> void:
	var program: RefCounted = game.get("program")
	if program == null:
		return
	for id: String in health_rows:
		(health_rows[id] as ProgressBar).value = float(program.get("health")[id]["value"])


func show_message(text: String, seconds: float) -> void:
	notifications.text = text.left(1024)
	message_remaining = seconds


func _process(delta: float) -> void:
	if game.get("state") == "paused":
		return
	refresh_health()
	if message_remaining > 0:
		message_remaining -= delta
		if message_remaining <= 0:
			notifications.text = ""
