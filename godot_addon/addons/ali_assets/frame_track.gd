@tool
extends VBoxContainer
signal clip_saved(path: String, clip: String, looped: bool, reversed: bool, speed: float)
const TrackIO: GDScript = preload("frame_track_io.gd")
const Drop: GDScript = preload("asset_drop.gd")
var strip: HBoxContainer
var picture: TextureRect
var caption: Label
var fps: SpinBox
var speed: SpinBox
var hold: SpinBox
var loop: CheckBox
var reverse: CheckBox
var name_edit: LineEdit
var play_button: Button
var apply_button: Button
var clips: OptionButton
var chooser: FileDialog
var clock: Timer
var frames: SpriteFrames
var current_clip: String = ""
var frame_index: int = 0
var key: String = ""


func _ready() -> void:
	var toolbar: HBoxContainer = HBoxContainer.new()
	add_child(toolbar)
	var title: Label = Label.new()
	title.text = "动画轴"
	title.add_theme_font_size_override("font_size",16)
	toolbar.add_child(title)
	picture = TextureRect.new()
	picture.custom_minimum_size = Vector2(108,104)
	picture.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	picture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	picture.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var content: HBoxContainer = HBoxContainer.new()
	content.add_child(picture)
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.custom_minimum_size.y = 104
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	content.add_child(scroll)
	strip = HBoxContainer.new()
	scroll.add_child(strip)
	add_child(content)
	caption = Label.new()
	caption.text = "将动画 ZIP、图片文件夹或多张图片拖到这里"
	caption.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(caption)
	clips = OptionButton.new()
	clips.item_selected.connect(func(index: int) -> void: select_clip(clips.get_item_text(index)))
	toolbar.add_child(clips)
	name_edit = LineEdit.new()
	name_edit.placeholder_text = "片段名称"
	name_edit.custom_minimum_size.x = 108
	toolbar.add_child(name_edit)
	play_button = make_button(toolbar,"播放",toggle)
	make_button(toolbar,"←",func() -> void: move_frame(-1))
	make_button(toolbar,"→",func() -> void: move_frame(1))
	make_button(toolbar,"移除帧",remove_frame)
	make_button(toolbar,"选择素材…",func() -> void: chooser.popup_centered_ratio(0.65))
	apply_button = make_button(toolbar,"应用动画轴",save_clip)
	var options: HBoxContainer = HBoxContainer.new()
	add_child(options)
	fps = spin(options,"FPS",0.01,240,0.01,12)
	speed = spin(options,"速度",0.01,100,0.01,1)
	hold = spin(options,"帧时长倍率",0.01,100,0.01,1)
	hold.value_changed.connect(func(value: float) -> void:
		if frames != null:
			var texture: Texture2D = frames.get_frame_texture(current_clip,frame_index)
			frames.remove_frame(current_clip,frame_index)
			frames.add_frame(current_clip,texture,value,frame_index)
			update_status())
	loop = CheckBox.new()
	loop.text = "循环"
	options.add_child(loop)
	reverse = CheckBox.new()
	reverse.text = "反向"
	options.add_child(reverse)
	fps.value_changed.connect(func(_value: float) -> void: update_status())
	speed.value_changed.connect(func(_value: float) -> void: update_status())
	clock = Timer.new()
	clock.one_shot = true
	clock.timeout.connect(advance)
	add_child(clock)
	chooser = FileDialog.new()
	chooser.access = FileDialog.ACCESS_FILESYSTEM
	chooser.file_mode = FileDialog.FILE_MODE_OPEN_FILES
	chooser.filters = PackedStringArray(["*.zip, *.json, *.png, *.jpg, *.jpeg, *.webp, *.tres, *.res, *.tscn ; 动画资源"])
	chooser.files_selected.connect(import_paths)
	add_child(chooser)
	var can_drop: Callable = func(_position: Vector2, payload: Variant) -> bool: return TrackIO.acceptable(TrackIO.from_payload(payload))
	var drop: Callable = func(_position: Vector2, payload: Variant) -> void: import_paths(TrackIO.from_payload(payload))
	for control: Control in [self,strip,content,scroll]:
		control.set_drag_forwarding(Callable(),can_drop,drop)
	get_window().files_dropped.connect(on_files_dropped)
	refresh()


func on_files_dropped(paths: PackedStringArray) -> void:
	if Drop.contains(self,Vector2(DisplayServer.mouse_get_position())):
		import_paths(paths)


func make_button(parent: Node, text: String, action: Callable) -> Button:
	var button: Button = Button.new()
	button.text = text
	button.pressed.connect(action)
	parent.add_child(button)
	return button


func spin(parent: Node, caption_text: String, low: float, high: float, step: float, value: float) -> SpinBox:
	var label: Label = Label.new()
	label.text = caption_text
	parent.add_child(label)
	var input: SpinBox = SpinBox.new()
	input.min_value = low
	input.max_value = high
	input.step = step
	input.value = value
	parent.add_child(input)
	return input


func bind(next_key: String, path: String, params: Dictionary) -> void:
	if key == next_key: return
	key = next_key
	stop()
	frames = null
	current_clip = ""
	name_edit.clear()
	if not path.is_empty() and ResourceLoader.exists(path):
		var prepared: Dictionary = TrackIO.read(PackedStringArray([path]))
		if prepared.has("frames"):
			load_frames(prepared["frames"],str(params.get("clip",prepared["clip"])))
			if params.has("loops"): loop.button_pressed = int(params["loops"]) == 0
	speed.value = float(params.get("speed",1))
	reverse.button_pressed = bool(params.get("reverse",false))
	refresh()


func import_paths(paths: PackedStringArray) -> void:
	var prepared: Dictionary = TrackIO.read(paths)
	if prepared.has("error"):
		caption.text = prepared["error"]
		return
	load_frames(prepared["frames"],prepared["clip"])
	caption.text += " · 点击「应用动画轴」绑定"


func load_frames(resource: SpriteFrames, clip: String) -> void:
	frames = resource.duplicate() as SpriteFrames
	var names: PackedStringArray = Drop.clips(frames)
	select_clip(clip if clip in names else names[0])


func select_clip(clip: String) -> void:
	stop()
	current_clip = clip
	name_edit.text = clip
	fps.set_value_no_signal(frames.get_animation_speed(clip))
	loop.button_pressed = frames.get_animation_loop(clip)
	frame_index = 0
	refresh()


func refresh() -> void:
	for child: Node in strip.get_children():
		strip.remove_child(child)
		child.queue_free()
	clips.clear()
	apply_button.disabled = frames == null
	play_button.disabled = frames == null
	if frames != null:
		for clip: String in Drop.clips(frames): clips.add_item(clip)
		clips.select(Drop.clips(frames).find(current_clip))
		var count: int = frames.get_frame_count(current_clip)
		var buttons: ButtonGroup = ButtonGroup.new()
		for index: int in range(count):
			var frame: Button = make_button(strip,str(index+1),func() -> void: seek(index))
			frame.custom_minimum_size = Vector2(62,80)
			frame.icon = frames.get_frame_texture(current_clip,index)
			frame.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
			frame.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
			frame.expand_icon = true
			frame.add_theme_constant_override("icon_max_width",44)
			frame.toggle_mode = true
			frame.button_group = buttons
			frame.mouse_filter = Control.MOUSE_FILTER_PASS
			frame.set_drag_forwarding(Callable(),
				func(_position: Vector2,payload: Variant) -> bool: return TrackIO.acceptable(TrackIO.from_payload(payload)),
				func(_position: Vector2,payload: Variant) -> void: import_paths(TrackIO.from_payload(payload)))
		seek(clampi(frame_index,0,count-1))
	else:
		picture.texture = null
		update_status()


func seek(index: int) -> void:
	if frames == null: return
	frame_index = index
	var button: Button = strip.get_child(index) as Button
	button.set_pressed_no_signal(true)
	ensure_selected.call_deferred()
	picture.texture = frames.get_frame_texture(current_clip,index)
	hold.set_value_no_signal(frames.get_frame_duration(current_clip,index))
	update_status()


func ensure_selected() -> void:
	if not is_inside_tree() or frame_index >= strip.get_child_count(): return
	var scroll: ScrollContainer = strip.get_parent() as ScrollContainer
	scroll.ensure_control_visible(strip.get_child(frame_index) as Control)


func update_status() -> void:
	if frames == null:
		caption.text = "拖入动画 ZIP、图片文件夹、PNG 序列或 SpriteFrames"
		return
	var duration: float = 0.0
	var count: int = frames.get_frame_count(current_clip)
	for index: int in range(count): duration += frames.get_frame_duration(current_clip,index)
	caption.text = "第 %d / %d 帧 · %.2f 秒" % [frame_index+1,count,duration / fps.value / speed.value]


func move_frame(direction: int) -> void:
	if frames == null: return
	var destination: int = frame_index+direction
	if destination < 0 or destination >= strip.get_child_count(): return
	stop()
	var texture: Texture2D = frames.get_frame_texture(current_clip,frame_index)
	var duration: float = frames.get_frame_duration(current_clip,frame_index)
	frames.remove_frame(current_clip,frame_index)
	frames.add_frame(current_clip,texture,duration,destination)
	frame_index = destination
	refresh()


func remove_frame() -> void:
	if frames == null or strip.get_child_count() <= 1: return
	stop()
	frames.remove_frame(current_clip,frame_index)
	refresh()


func stop() -> void:
	clock.stop()
	play_button.text = "播放"


func toggle() -> void:
	if not clock.is_stopped():
		stop()
	elif frames != null:
		seek(strip.get_child_count()-1 if reverse.button_pressed else 0)
		play_button.text = "暂停"
		clock.start(maxf(0.005,hold.value / fps.value / speed.value))


func advance() -> void:
	var next: int = frame_index + (-1 if reverse.button_pressed else 1)
	var count: int = strip.get_child_count()
	if not loop.button_pressed and (next < 0 or next >= count):
		stop()
		return
	seek(posmod(next,count))
	clock.start(maxf(0.005,hold.value / fps.value / speed.value))


func save_clip() -> void:
	if frames == null: return
	stop()
	var name: String = name_edit.text.strip_edges()
	if name.is_empty() or "/" in name or ":" in name or "," in name:
		caption.text = "请输入有效的片段名称。"
		return
	var output: SpriteFrames = SpriteFrames.new()
	output.remove_animation("default")
	Drop.copy_clip(output,name,frames,current_clip)
	output.set_animation_speed(name,fps.value)
	output.set_animation_loop(name,loop.button_pressed)
	var path: String = TrackIO.save(output)
	if path.is_empty():
		caption.text = "保存动画资源失败。"
		return
	clip_saved.emit(path,name,loop.button_pressed,reverse.button_pressed,speed.value)
