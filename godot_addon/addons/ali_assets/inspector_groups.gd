@tool
extends RefCounted
## Small, persistent inspector folds shared by both graph editors.


static func add(parent: VBoxContainer, key: String, title: String, open: bool = true) -> VBoxContainer:
	var panel: VBoxContainer = VBoxContainer.new()
	parent.add_child(panel)
	var toggle: Button = Button.new()
	toggle.alignment = HORIZONTAL_ALIGNMENT_LEFT
	toggle.toggle_mode = true
	var settings: EditorSettings = EditorInterface.get_editor_settings()
	toggle.button_pressed = bool(settings.get_project_metadata("ali_blueprint_folds", key, open))
	panel.add_child(toggle)
	var body: VBoxContainer = VBoxContainer.new()
	panel.add_child(body)
	var update: Callable = func(value: bool) -> void:
		toggle.text = ("▼ " if value else "▶ ") + title
		body.visible = value
	update.call(toggle.button_pressed)
	toggle.toggled.connect(func(value: bool) -> void:
		update.call(value)
		settings.set_project_metadata("ali_blueprint_folds", key, value))
	return body
