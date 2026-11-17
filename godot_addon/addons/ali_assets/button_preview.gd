@tool
extends Window
const Widgets: GDScript = preload("game_widgets.gd")
var sound: AudioStreamPlayer


func _init() -> void:
	visible = false
	force_native = true


func present(p: Dictionary) -> void:
	title = "按钮预览 · 独立副本"
	size = Vector2i(600, 460)
	close_requested.connect(func() -> void: sound.stop(); hide(); queue_free())
	var root: VBoxContainer = VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(root)
	var note: Label = Label.new()
	note.text = "移动鼠标／按下按钮查看状态；空状态图沿用普通图。\n此预览不修改绑定场景，不触发游戏蓝图。"
	root.add_child(note)
	var button: BaseButton
	if p["widget"] == "texture":
		button = TextureButton.new()
	else:
		button = Button.new()
	if button is TextureButton:
		(button as TextureButton).ignore_texture_size = true
		(button as TextureButton).stretch_mode = TextureButton.STRETCH_KEEP_ASPECT_CENTERED
	button.custom_minimum_size = Vector2(200, 140)
	Widgets.decorate(button, p)
	root.add_child(button)
	sound = AudioStreamPlayer.new()
	sound.volume_db = float(p["volume"])
	add_child(sound)
	button.mouse_entered.connect(func() -> void: play(p, "hover_sound", button))
	button.pressed.connect(func() -> void: play(p, "click_sound", button))
	var disabled: CheckBox = CheckBox.new()
	disabled.text = "禁用状态"
	disabled.button_pressed = bool(p["disabled"])
	disabled.toggled.connect(func(value: bool) -> void: button.disabled = value)
	root.add_child(disabled)
	var states: OptionButton = OptionButton.new()
	for caption: String in ["普通贴图", "悬停贴图", "按下贴图", "禁用贴图"]:
		states.add_item(caption)
	root.add_child(states)
	var image: TextureRect = TextureRect.new()
	image.custom_minimum_size = Vector2(200, 110)
	image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	root.add_child(image)
	var show_state: Callable = func(index: int) -> void:
		var key: String = ["normal_texture", "hover_texture", "pressed_texture", "disabled_texture"][index]
		image.texture = Widgets.texture(p, key)
		if image.texture == null:
			image.texture = Widgets.texture(p, "normal_texture")
	states.item_selected.connect(show_state)
	show_state.call(0)
	popup_centered()


func play(p: Dictionary, key: String, button: BaseButton) -> void:
	if button.disabled or str(p[key]).is_empty():
		return
	sound.stream = load(str(p[key])) as AudioStream
	sound.play()


func _exit_tree() -> void:
	if is_instance_valid(sound):
		sound.stop()
