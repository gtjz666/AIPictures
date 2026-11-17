@tool
extends Window
const Builder: GDScript = preload("framework_builder.gd")
var folder: LineEdit
var preset: OptionButton
var set_main: CheckBox
var status: Label


func _init() -> void:
	visible = false
	force_native = true


func _ready() -> void:
	title = "AlI · 创建2D游戏框架"
	size = Vector2i(620,360)
	close_requested.connect(hide)
	var box: VBoxContainer = VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	box.offset_left = 20
	box.offset_top = 20
	box.offset_right = -20
	box.offset_bottom = -20
	add_child(box)
	var hint: Label = Label.new()
	hint.text = "创建原生可编辑的主菜单、游戏、暂停、设置、存取与结束界面。\n选择一个新目录；不会覆盖已有文件。"
	box.add_child(hint)
	folder = LineEdit.new()
	folder.text = "res://".path_join("games/my_game")
	folder.placeholder_text = "项目内新目录 res://…"
	box.add_child(folder)
	preset = OptionButton.new()
	for key: String in Builder.PRESETS:
		preset.add_item(Builder.PRESETS[key])
		preset.set_item_metadata(preset.item_count-1,key)
	box.add_child(preset)
	set_main = CheckBox.new()
	set_main.text = "创建后设为项目启动场景"
	box.add_child(set_main)
	var create: Button = Button.new()
	create.text = "创建游戏框架"
	box.add_child(create)
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(status)
	create.pressed.connect(func() -> void:
		var result: Dictionary = Builder.create(folder.text.strip_edges(),str(preset.get_item_metadata(preset.selected)),set_main.button_pressed)
		status.text = str(result.get("error","已创建："+folder.text+"。从MainMenu运行，或打开Game编辑。"))
		if not result.has("error"):
			EditorInterface.get_resource_filesystem().scan()
			EditorInterface.open_scene_from_path(str(result["scene"])))
