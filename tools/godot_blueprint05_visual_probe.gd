@tool
extends EditorPlugin
const Model: GDScript = preload("res://addons/ali_assets/game_model.gd")
const ButtonPreview: GDScript = preload("res://addons/ali_assets/button_preview.gd")
const Browser: GDScript = preload("res://addons/ali_assets/resource_browser.gd")


func _enter_tree() -> void:
	run.call_deferred()


func run() -> void:
	await get_tree().create_timer(1.0).timeout
	var ali: Node = get_tree().get_first_node_in_group("ali_assets_editor")
	ali.call("open_game_window")
	var window: Window = ali.get("game_window") as Window
	window.size = Vector2i(1520, 940)
	var data: Dictionary = Model.scene_preset()
	var button: Dictionary = Model.module("start_button", "button", 610, 60)
	button["params"].merge({"text":"开始冒险", "normal_texture":"res://fixtures/button.png", "hover_texture":"res://fixtures/sky.png", "pressed_texture":"res://fixtures/ground.png", "click_sound":"res://fixtures/tone.wav"}, true)
	var message: Dictionary = Model.module("message", "ui_message", 970, 60)
	message["params"]["text"] = "按钮事件已连接"
	data["nodes"].append_array([button, message])
	data["edges"].append({"from":"start_button","from_port":0,"to":"message","to_port":0})
	window.call("change", "按钮展示", data)
	window.set("selected_id", "start_button")
	window.call("show_inspector")
	(window.get("graph") as GraphEdit).scroll_offset = Vector2(-30, -30)
	await get_tree().create_timer(0.5).timeout
	RenderingServer.force_draw()
	assert(window.get_texture().get_image().save_png("res://blueprint05-editor.png") == OK)
	var preview: Window = ButtonPreview.new()
	add_child(preview)
	preview.call("present", button["params"])
	await get_tree().create_timer(0.3).timeout
	RenderingServer.force_draw()
	assert(preview.get_texture().get_image().save_png("res://blueprint05-button.png") == OK)
	preview.queue_free()
	var browser: Window = Browser.new()
	add_child(browser)
	browser.popup_centered()
	assert(browser.visible)
	browser.queue_free()
	window.hide()
	get_tree().quit.call_deferred(0)
