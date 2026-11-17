@tool
extends Window
const Importer: GDScript = preload("asset_import.gd")
var import_mode: OptionButton
var clip: LineEdit
var cell_x: SpinBox
var cell_y: SpinBox
var margin_x: SpinBox
var margin_y: SpinBox
var gap_x: SpinBox
var gap_y: SpinBox
var columns: SpinBox
var rows: SpinBox
var fps: SpinBox
var looping: CheckBox
var reverse: CheckBox
var output_animation: CheckBox
var target_path: LineEdit
var grid: ItemList
var status: Label
var files: FileDialog
var destination: FileDialog
var paths: PackedStringArray = []
var textures: Array[Texture2D] = []
var source_slot: Control


func _init() -> void:
	visible = false
	force_native = true


func _ready() -> void:
	title = "AlI · 动画／瓦片图集导入"
	size = Vector2i(880,720)
	close_requested.connect(hide)
	var box: VBoxContainer = VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(box)
	import_mode = OptionButton.new()
	for text: String in ["连续图片→SpriteFrames","Sprite Sheet→SpriteFrames","瓦片图集→TileSet"]: import_mode.add_item(text)
	box.add_child(import_mode)
	import_mode.item_selected.connect(func(_index: int) -> void: refresh())
	var choose: Button = Button.new()
	choose.text = "选择项目内图片…（也可将文件拖到此处）"
	choose.pressed.connect(func() -> void: files.popup_centered_ratio(0.7))
	choose.set_drag_forwarding(Callable(),func(_at: Vector2,data: Variant) -> bool: return data is Dictionary and data.get("type") == "files",func(_at: Vector2,data: Variant) -> void: select_files(PackedStringArray(data["files"])))
	box.add_child(choose)
	var form: GridContainer = GridContainer.new()
	form.columns = 6
	box.add_child(form)
	cell_x = number(form,"格宽",32,1,4096)
	cell_y = number(form,"格高",32,1,4096)
	fps = number(form,"帧率",12,1,240)
	margin_x = number(form,"左边距",0,0,4096)
	margin_y = number(form,"上边距",0,0,4096)
	gap_x = number(form,"横间距",0,0,4096)
	gap_y = number(form,"竖间距",0,0,4096)
	columns = number(form,"列数反算",0,0,4096)
	rows = number(form,"行数反算",0,0,4096)
	var counts: Button = Button.new()
	counts.text = "按行列计算格宽高"
	counts.pressed.connect(from_counts)
	box.add_child(counts)
	clip = LineEdit.new()
	clip.text = "default"
	clip.placeholder_text = "动画名称"
	box.add_child(clip)
	looping = CheckBox.new()
	looping.text = "循环"
	looping.button_pressed = true
	box.add_child(looping)
	reverse = CheckBox.new()
	reverse.text = "反转帧顺序（默认自然文件名顺序，按住Ctrl可选择部分帧／瓦片）"
	box.add_child(reverse)
	output_animation = CheckBox.new()
	output_animation.text = "输出Animation资源（默认输出SpriteFrames；轨道用于Sprite2D.texture）"
	box.add_child(output_animation)
	target_path = LineEdit.new()
	target_path.text = "Visual"
	target_path.placeholder_text = "Animation轨道目标相对路径"
	box.add_child(target_path)
	grid = ItemList.new()
	grid.select_mode = ItemList.SELECT_MULTI
	grid.max_columns = 0
	grid.fixed_column_width = 100
	grid.fixed_icon_size = Vector2i(72,72)
	grid.icon_mode = ItemList.ICON_MODE_TOP
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(grid)
	var order: HBoxContainer = HBoxContainer.new()
	box.add_child(order)
	for entry: Array in [["所选帧上移",-1],["所选帧下移",1]]:
		var move: Button = Button.new()
		move.text = entry[0]
		move.pressed.connect(func() -> void: move_frame(int(entry[1])))
		order.add_child(move)
	var save: Button = Button.new()
	save.text = "创建新资源…"
	save.pressed.connect(func() -> void: destination.current_file = "tileset.tres" if import_mode.selected == 2 else "animation.tres" if output_animation.button_pressed else "sprite_frames.tres"; destination.popup_centered_ratio(0.7))
	box.add_child(save)
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(status)
	files = FileDialog.new()
	files.access = FileDialog.ACCESS_RESOURCES
	files.file_mode = FileDialog.FILE_MODE_OPEN_FILES
	files.filters = PackedStringArray(["*.png,*.webp,*.jpg ; 图片"])
	files.files_selected.connect(select_files)
	add_child(files)
	destination = FileDialog.new()
	destination.access = FileDialog.ACCESS_RESOURCES
	destination.file_mode = FileDialog.FILE_MODE_SAVE_FILE
	destination.filters = PackedStringArray(["*.tres ; 原生资源"])
	destination.file_selected.connect(save_to)
	add_child(destination)


func number(parent: Control, label: String, value: float, minimum: float, maximum: float) -> SpinBox:
	var caption: Label = Label.new()
	caption.text = label
	parent.add_child(caption)
	var spin: SpinBox = SpinBox.new()
	spin.min_value = minimum
	spin.max_value = maximum
	spin.value = value
	spin.value_changed.connect(func(_value: float) -> void: if is_instance_valid(grid): refresh())
	parent.add_child(spin)
	return spin


func select_files(selected: PackedStringArray) -> void:
	paths = Importer.ordered(selected)
	refresh()


func from_counts() -> void:
	if paths.size() != 1: status.text = "先选择单张图集"; return
	var texture: Texture2D = load(paths[0]) as Texture2D
	if texture == null: return
	if columns.value > 0: cell_x.value = floor((texture.get_width()-margin_x.value-(columns.value-1)*gap_x.value)/columns.value)
	if rows.value > 0: cell_y.value = floor((texture.get_height()-margin_y.value-(rows.value-1)*gap_y.value)/rows.value)
	refresh()


func options() -> Dictionary:
	var selected: Array = []
	for index: int in grid.get_selected_items(): selected.append(index)
	return {"sheet":import_mode.selected != 0,"sort":false,"cell":Vector2i(int(cell_x.value),int(cell_y.value)),"margin":Vector2i(int(margin_x.value),int(margin_y.value)),"gap":Vector2i(int(gap_x.value),int(gap_y.value)),"fps":fps.value,"clip":clip.text,"loop":looping.button_pressed,"reverse":reverse.button_pressed,"selection":selected}


func move_frame(direction: int) -> void:
	var selection: PackedInt32Array = grid.get_selected_items()
	if import_mode.selected != 0 or selection.size() != 1: status.text = "连续图片模式中选择一帧后调整顺序"; return
	var at: int = selection[0]
	var next: int = at+direction
	if next < 0 or next >= paths.size(): return
	var original: String = paths[at]
	paths[at] = paths[next]
	paths[next] = original
	refresh()
	grid.select(next)


func refresh() -> void:
	grid.clear()
	textures.clear()
	if paths.is_empty(): return
	if import_mode.selected == 0:
		for path: String in paths:
			var texture: Texture2D = load(path) as Texture2D
			if texture == null: continue
			textures.append(texture)
			grid.add_item(path.get_file(),texture)
	else:
		if paths.size() != 1: status.text = "图集模式请选择一张图"; return
		var texture: Texture2D = load(paths[0]) as Texture2D
		var boxes: Array[Rect2i] = Importer.regions(texture,Vector2i(int(cell_x.value),int(cell_y.value)),Vector2i(int(margin_x.value),int(margin_y.value)),Vector2i(int(gap_x.value),int(gap_y.value)))
		for index: int in range(boxes.size()):
			var atlas: AtlasTexture = AtlasTexture.new()
			atlas.atlas = texture
			atlas.region = Rect2(boxes[index])
			textures.append(atlas)
			grid.add_item(str(index)+" · "+str(boxes[index].position),atlas)
	status.text = "预览%d项；未选择时导入全部。TileSet只切片，地形与碰撞请在Godot原生编辑器配置。" % textures.size()


func save_to(path: String) -> void:
	var p: Dictionary = options()
	var selected_paths: PackedStringArray = paths
	if import_mode.selected == 0 and not grid.get_selected_items().is_empty():
		selected_paths = []
		for index: int in grid.get_selected_items(): selected_paths.append(paths[index])
	var result: Dictionary = Importer.tileset(paths[0] if not paths.is_empty() else "",p) if import_mode.selected == 2 else Importer.frames(selected_paths,p)
	if result.has("error"): status.text = str(result["error"]); return
	var resource: Resource = result["resource"]
	if import_mode.selected != 2 and output_animation.button_pressed: resource = Importer.animation(resource as SpriteFrames,clip.text,target_path.text)
	var error: String = Importer.save(resource,path)
	status.text = error if not error.is_empty() else "已创建%d项：%s" % [result["count"],path]
	if error.is_empty(): EditorInterface.get_resource_filesystem().scan(); EditorInterface.edit_resource(resource)
