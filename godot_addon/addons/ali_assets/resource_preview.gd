@tool
extends Window
## Isolated native preview. User scenes and method tracks are never executed.
const Link: GDScript = preload("resource_link.gd")
var sound: AudioStreamPlayer
var sprite: AnimatedSprite2D
var player: AnimationPlayer
var ghost: ColorRect
var clips: OptionButton
var note: Label
var stage: Control


func _init() -> void:
	visible = false
	force_native = true


func present(resource: Resource) -> void:
	title = "资源预览 · " + resource.get_class()
	size = Vector2i(640, 520)
	close_requested.connect(finish)
	var root: VBoxContainer = VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(root)
	note = Label.new()
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	root.add_child(note)
	stage = Control.new()
	stage.custom_minimum_size = Vector2(600, 360)
	stage.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stage.clip_contents = true
	root.add_child(stage)
	var backdrop: ColorRect = ColorRect.new()
	backdrop.color = Color("292f3b")
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	stage.add_child(backdrop)
	var controls: HBoxContainer = HBoxContainer.new()
	root.add_child(controls)
	clips = OptionButton.new()
	controls.add_child(clips)
	add_button(controls, "▶ 播放", play)
	add_button(controls, "Ⅱ 暂停", pause)
	add_button(controls, "■ 停止／复位", stop)
	if resource is Texture2D:
		var image: TextureRect = TextureRect.new()
		image.texture = resource as Texture2D
		image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		image.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		stage.add_child(image)
		note.text = "%s · %s" % [resource.resource_path, (resource as Texture2D).get_size()]
		controls.hide()
	elif resource is AudioStream:
		sound = AudioStreamPlayer.new()
		sound.stream = resource as AudioStream
		sound.volume_db = -14
		add_child(sound)
		note.text = "手动试听 · %.2f秒 · 关闭窗口停止播放" % sound.stream.get_length()
		clips.hide()
	elif Link.frames(resource) != null:
		sprite = AnimatedSprite2D.new()
		sprite.sprite_frames = Link.frames(resource).duplicate(true) as SpriteFrames
		sprite.position = Vector2(300, 180)
		stage.add_child(sprite)
		for clip: StringName in sprite.sprite_frames.get_animation_names():
			clips.add_item(str(clip))
		clips.item_selected.connect(select_clip)
		if clips.item_count > 0:
			select_clip(0)
		note.text = "SpriteFrames副本 · 选择片段后手动播放 · 原场景不会实例化"
	elif resource is Animation or resource is AnimationLibrary:
		setup_animation(resource)
	else:
		note.text = resource.resource_path + "\n类型：" + resource.get_class() + "\n此类型在Godot检查器中编辑；此窗口不执行场景或脚本。"
		controls.hide()
		if Engine.is_editor_hint():
			add_button(root, "在Godot检查器中查看", func() -> void: EditorInterface.inspect_object(resource))
	popup_centered()


func add_button(parent: Node, label: String, callback: Callable) -> void:
	var button: Button = Button.new()
	button.text = label
	button.pressed.connect(callback)
	parent.add_child(button)


func setup_animation(resource: Resource) -> void:
	ghost = ColorRect.new()
	ghost.name = "Ghost"
	ghost.color = Color("6bb5e4")
	ghost.size = Vector2(64, 64)
	ghost.position = Vector2(260, 140)
	stage.add_child(ghost)
	player = AnimationPlayer.new()
	stage.add_child(player)
	var library: AnimationLibrary = AnimationLibrary.new()
	var source: AnimationLibrary = resource as AnimationLibrary
	if resource is Animation:
		source = AnimationLibrary.new()
		source.add_animation(&"preview", resource as Animation)
	var skipped: int = 0
	for clip: StringName in source.get_animation_list():
		var animation: Animation = source.get_animation(clip).duplicate(true) as Animation
		for track: int in range(animation.get_track_count()):
			var path: NodePath = animation.track_get_path(track)
			var property: String = str(path.get_concatenated_subnames())
			var accepted: bool = animation.track_get_type(track) == Animation.TYPE_VALUE and property in ["position", "scale", "rotation", "modulate", "self_modulate", "size", "pivot_offset", "visible"]
			for key: int in range(animation.track_get_key_count(track)):
				accepted = accepted and typeof(animation.track_get_key_value(track, key)) == typeof(ghost.get(property)) if property in ["position", "scale", "rotation", "modulate", "self_modulate", "size", "pivot_offset", "visible"] else false
			animation.track_set_enabled(track, accepted)
			if accepted:
				animation.track_set_path(track, NodePath("Ghost:" + property))
			else:
				skipped += 1
		library.add_animation(clip, animation)
		clips.add_item(str(clip))
	player.add_animation_library(&"", library)
	clips.item_selected.connect(select_clip)
	note.text = "隔离2D属性预览 · 已跳过%d条非兼容轨道（方法、音频、3D、其他属性）\n不会驱动原场景；运行目标绑定待后续2D阶段提供，3D制作暂缓。" % skipped


func select_clip(index: int) -> void:
	stop()
	if sprite != null:
		sprite.animation = clips.get_item_text(index)
		if sprite.sprite_frames.get_frame_count(sprite.animation) > 0:
			var texture: Texture2D = sprite.sprite_frames.get_frame_texture(sprite.animation, 0)
			if texture != null:
				sprite.scale = Vector2.ONE * minf(1, 320.0 / maxf(texture.get_width(), texture.get_height()))


func play() -> void:
	if sound != null:
		if sound.stream_paused:
			sound.stream_paused = false
		else:
			sound.play()
	if sprite != null:
		sprite.play()
	if player != null and clips.item_count > 0:
		player.play(clips.get_item_text(clips.selected))


func pause() -> void:
	if sound != null:
		sound.stream_paused = true
	if sprite != null:
		sprite.pause()
	if player != null:
		player.pause()


func stop() -> void:
	if sound != null:
		sound.stop()
		sound.stream_paused = false
	if sprite != null:
		sprite.stop()
	if player != null:
		player.stop()
		ghost.position = Vector2(260, 140)
		ghost.scale = Vector2.ONE
		ghost.rotation = 0
		ghost.modulate = Color.WHITE
		ghost.self_modulate = Color.WHITE
		ghost.size = Vector2(64, 64)
		ghost.pivot_offset = Vector2.ZERO
		ghost.show()


func finish() -> void:
	stop()
	hide()
	queue_free()


func _exit_tree() -> void:
	if is_instance_valid(sound):
		sound.stop()
