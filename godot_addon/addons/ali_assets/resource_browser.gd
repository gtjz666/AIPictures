@tool
extends Window
const Slot: GDScript = preload("resource_slot.gd")


func _init() -> void:
	visible = false
	force_native = true


func _ready() -> void:
	title = "资源预览台"
	size = Vector2i(520, 260)
	close_requested.connect(queue_free)
	var body: VBoxContainer = VBoxContainer.new()
	body.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(body)
	var hint: Label = Label.new()
	hint.text = "拖入图片、音频、SpriteFrames、Animation或AnimationLibrary预览。\n场景、TileSet和其他Resource可在检查器中编辑。\n通用动画／Camera2D节点另提供绑定目标的独立副本预览。"
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(hint)
	var slot: VBoxContainer = Slot.new()
	body.add_child(slot)
	slot.call("setup", "resource", "")
