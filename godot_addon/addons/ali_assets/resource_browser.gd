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
	hint.text = "拖入图片、音频、SpriteFrames、Animation或AnimationLibrary预览。\n场景、TileSet和其他Resource可查看类型并在检查器中编辑。\n动画预览台仅预览2D属性；运行绑定将在通用动画阶段提供。"
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(hint)
	var slot: VBoxContainer = Slot.new()
	body.add_child(slot)
	slot.call("setup", "resource", "")
