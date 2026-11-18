extends Control
## Native, editable menu scenes. Actions use shared services; motion uses Animation.
const Services: GDScript = preload("framework_services.gd")
@export var framework: Dictionary = {}
@export_enum("main","pause","settings","save","over") var menu_kind: String = "main"
@export var bindings: Dictionary = {}
@export var effects: Dictionary = {"enabled":true,"hover_scale":1.1,"pressed_scale":0.95,"seconds":0.12,"open_seconds":0.18,"slide_x":40.0}
@export var click_sound: AudioStream
@export var hover_sound: AudioStream
@export var overlay: bool = false
var service: Node
var voice: AudioStreamPlayer
var syncing: bool = false
var opening: RefCounted
var transient: Array[Control] = []


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	if menu_kind in ["pause", "over"]: hide()
	initialize_menu.call_deferred()


func initialize_menu() -> void:
	if not is_inside_tree(): return
	service = Services.obtain(get_tree(),framework,str(framework.get("key","ali_game")),Services)
	voice = AudioStreamPlayer.new()
	voice.process_mode = Node.PROCESS_MODE_ALWAYS
	add_child(voice)
	for button_name: String in bindings:
		var button: BaseButton = find_child(button_name,true,false) as BaseButton
		if button == null: continue
		button.pressed.connect(func() -> void: sound(click_sound); perform(str(bindings[button_name])))
		var baseline: Vector2 = button.scale
		button.mouse_entered.connect(func() -> void: sound(hover_sound); scale_button(button,baseline*float(effects.get("hover_scale",1.1))))
		button.mouse_exited.connect(func() -> void: scale_button(button,baseline))
		button.button_down.connect(func() -> void: scale_button(button,baseline*float(effects.get("pressed_scale",0.95))))
		button.button_up.connect(func() -> void: scale_button(button,baseline))
	if menu_kind == "pause":
		hide()
		service.get("bus").call("subscribe",self,"project:"+str(service.get("key")),"paused",func(_data: Variant) -> void: open_menu())
		service.get("bus").call("subscribe",self,"project:"+str(service.get("key")),"resumed",func(_data: Variant) -> void: close_menu(false))
	elif menu_kind == "over":
		hide()
		service.get("bus").call("subscribe",self,"project:"+str(service.get("key")),"ended",func(_data: Variant) -> void: open_menu())
	else: open_menu()
	if menu_kind == "settings": setup_settings()
	if menu_kind == "save": refresh_slots()
	if menu_kind == "main":
		var continuing: BaseButton = find_child("ContinueButton",true,false) as BaseButton
		if continuing != null: continuing.disabled = first_save_slot() < 0


func animation(p: Dictionary, target: Control) -> RefCounted:
	p["ui"] = true
	return service.get("scenes").get("animations").call("start",p,target) as RefCounted


func scale_button(button: BaseButton, value: Vector2) -> void:
	if effects.get("enabled",true) and not button.disabled: animation({"mode":"property","property":"scale","to":value,"seconds":effects.get("seconds",0.12)},button)


func sound(stream: AudioStream) -> void:
	if stream == null: return
	var game: Node = service.call("current_game") as Node
	voice.bus = str(game.get("bus_names")["UI"]) if game != null else "Master"
	var volume: Dictionary = service.get("settings").get("volumes",{})
	voice.volume_db = 0.0 if game != null else float(volume.get("Master",0))+float(volume.get("UI",-8))
	voice.stream = stream
	voice.play()


func open_menu() -> void:
	show()
	modulate.a = 0.0 if effects.get("enabled",true) else 1.0
	if effects.get("enabled",true): opening = animation({"mode":"property","property":"modulate:a","to":1.0,"seconds":effects.get("open_seconds",0.18)},self)
	var frame: Control = get_node_or_null("Frame") as Control
	if frame != null and effects.get("enabled",true) and menu_kind in ["settings","pause"]:
		var baseline: Vector2 = frame.position
		frame.position = baseline + Vector2(float(effects.get("slide_x",40)),0)
		animation({"mode":"property","property":"position","to":baseline,"seconds":effects.get("open_seconds",0.18)},frame)
	var buttons: Array[Node] = find_children("*","Button",true,false)
	if not buttons.is_empty(): (buttons[0] as Button).grab_focus()


func close_menu(free_after: bool = true) -> void:
	if effects.get("enabled",true):
		var task: RefCounted = animation({"mode":"property","property":"modulate:a","to":0.0,"seconds":effects.get("open_seconds",0.18)},self)
		if task.get("state") == "running": await task.settled
	hide()
	if free_after and overlay: queue_free()


func perform(action: String) -> void:
	match action:
		"start": service.get("scenes").call("request",str(framework.get("game_scene","")),0.2)
		"continue":
			var slot: int = first_save_slot()
			if slot >= 0: service.call("load_slot",slot)
		"resume": service.call("lifecycle","resume")
		"restart": close_menu(false); service.call("lifecycle","restart")
		"menu": service.call("lifecycle","menu")
		"quit": service.call("lifecycle","quit")
		"settings": open_overlay("settings_scene")
		"save","load": open_overlay("save_scene")
		"close":
			if overlay: close_menu()
			else: service.get("scenes").call("request",str(framework.get("menu_scene","")),0.15)
		"reset":
			service.call("settings_operation",{"operation":"reset"},0.0)
			setup_settings()
		_:
			if action.begins_with("save:"):
				service.call("save_slot",int(action.get_slice(":",1)))
				show_status("已保存" if str(service.get("last_error")).is_empty() else str(service.get("last_error")))
				refresh_slots()
			elif action.begins_with("load:"): service.call("load_slot",int(action.get_slice(":",1)))
			elif action.begins_with("delete:"):
				var error: String = service.get("storage").call("remove",int(action.get_slice(":",1)))
				show_status("已删除" if error.is_empty() else error)
				refresh_slots()


func open_overlay(field: String) -> void:
	transient = transient.filter(func(existing_panel: Control) -> bool: return is_instance_valid(existing_panel) and not existing_panel.is_queued_for_deletion())
	if not transient.is_empty(): return
	var path: String = str(framework.get(field,""))
	if not ResourceLoader.exists(path): show_status("未配置界面场景："+field); return
	var packed: PackedScene = load(path) as PackedScene
	if packed == null: show_status("界面不是PackedScene"); return
	var panel: Control = packed.instantiate() as Control
	if panel == null: return
	panel.set("overlay",true)
	add_child(panel)
	panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	transient.append(panel)


func first_save_slot() -> int:
	for row: Dictionary in service.get("storage").call("slots"):
		if row["valid"]: return int(row["slot"])
	return -1


func refresh_slots() -> void:
	var slots: Array = service.get("storage").call("slots")
	for slot: int in range(1,4):
		var row: Dictionary = slots[slot]
		var title: Label = find_child("SlotTitle"+str(slot),true,false) as Label
		if title != null: title.text = "槽位%d · %s" % [slot,row["saved_at"] if row["valid"] else row["error"] if row["exists"] else "空"]
		var load_button: BaseButton = find_child("LoadSlot"+str(slot),true,false) as BaseButton
		if load_button != null: load_button.disabled = not row["valid"]
		var save_button: BaseButton = find_child("SaveSlot"+str(slot),true,false) as BaseButton
		if save_button != null: save_button.disabled = service.call("current_game") == null
		var delete_button: BaseButton = find_child("DeleteSlot"+str(slot),true,false) as BaseButton
		if delete_button != null: delete_button.disabled = not row["exists"]


func setup_settings() -> void:
	syncing = true
	var current: Dictionary = service.get("settings")
	for channel: String in ["Master","BGM","SFX","UI"]:
		var slider: HSlider = find_child(channel+"Slider",true,false) as HSlider
		if slider == null: continue
		slider.value = float(current.get("volumes",{}).get(channel,0.0))
		if not slider.has_meta("bound"):
			slider.value_changed.connect(func(value: float) -> void:
				if not syncing: service.call("settings_operation",{"operation":"volume","channel":channel},value))
			slider.set_meta("bound",true)
	var window_mode: OptionButton = find_child("WindowMode",true,false) as OptionButton
	if window_mode != null:
		window_mode.select(["windowed","fullscreen","borderless"].find(str(current.get("window","windowed"))))
		if not window_mode.has_meta("bound"):
			window_mode.item_selected.connect(func(index: int) -> void:
				if not syncing: service.call("settings_operation",{"operation":"window","window":["windowed","fullscreen","borderless"][index]},0.0))
			window_mode.set_meta("bound",true)
	var resolution: OptionButton = find_child("Resolution",true,false) as OptionButton
	if resolution != null and not resolution.has_meta("bound"):
		resolution.item_selected.connect(func(index: int) -> void:
			if syncing: return
			var value: Vector2i = [Vector2i(960,540),Vector2i(1280,720),Vector2i(1920,1080)][index]
			service.call("settings_operation",{"operation":"resolution","width":value.x,"height":value.y},0.0))
		resolution.set_meta("bound",true)
	for action: String in service.get("inputs").get("defaults"):
		var button: Button = find_child("Bind_"+action,true,false) as Button
		if button == null: continue
		var labels: Array[String] = []
		for event: InputEvent in InputMap.action_get_events(action): labels.append(event.as_text())
		button.text = action+" · "+", ".join(labels)
		if not button.has_meta("bound"):
			button.pressed.connect(func() -> void:
				show_status("按下新按键／鼠标键；Esc取消，已有冲突会拒绝。")
				service.get("inputs").call("begin_capture",action,"reject"))
			button.set_meta("bound",true)
	if not has_meta("input_bound"):
		service.get("inputs").connect("capture_finished",func(_action: String,error: String) -> void: show_status("键位已保存" if error.is_empty() else error); setup_settings())
		set_meta("input_bound",true)
	syncing = false


func show_status(text: String) -> void:
	var status: Label = find_child("Status",true,false) as Label
	if status == null: return
	status.text = text
	status.modulate.a = 1.0
	animation({"mode":"property","property":"modulate:a","to":0.0,"delay":2.0,"seconds":0.6},status)


func _exit_tree() -> void:
	if is_instance_valid(service) and service.get("bus") != null: service.get("bus").call("unsubscribe",self)
	if is_instance_valid(voice): voice.stop()
