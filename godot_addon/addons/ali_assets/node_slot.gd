@tool
extends HBoxContainer
signal value_changed(path: String)
signal node_chosen(path: String, node: Node)
const Types: GDScript = preload("blueprint_types.gd")
var base: Node
var edit: LineEdit
var expected: String = "Node"


func setup(root: Node, value: String, wanted: String = "Node") -> void:
	base = root
	expected = wanted
	edit = LineEdit.new()
	edit.text = value
	edit.placeholder_text = "拖入场景节点或填相对路径"
	edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	edit.text_submitted.connect(func(path: String) -> void:
		if path.is_empty() or Types.relative_path(path): value_changed.emit(path)
		else: edit.tooltip_text = "需要当前游戏根节点下的相对路径")
	edit.set_drag_forwarding(Callable(),_can_drop_data,_drop_data)
	add_child(edit)
	var pick: Button = Button.new()
	pick.text = "使用选中"
	pick.pressed.connect(func() -> void:
		var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
		if selected.size() == 1: choose(selected[0]))
	pick.set_drag_forwarding(Callable(),_can_drop_data,_drop_data)
	add_child(pick)


func dragged(data: Variant) -> Node:
	if not data is Dictionary or data.get("type") != "nodes" or data.get("nodes",[]).size() != 1: return null
	return get_tree().root.get_node_or_null(NodePath(str(data["nodes"][0])))


func accepts(node: Node) -> bool:
	return is_instance_valid(base) and is_instance_valid(node) and (base == node or base.is_ancestor_of(node)) and node.is_class(expected)


func _can_drop_data(_at: Vector2, data: Variant) -> bool:
	return accepts(dragged(data))


func _drop_data(_at: Vector2, data: Variant) -> void:
	choose(dragged(data))


func choose(node: Node) -> void:
	if not accepts(node):
		edit.tooltip_text = "请选择当前游戏根节点内的" + expected
		return
	var path: String = str(base.get_path_to(node))
	edit.text = path
	value_changed.emit(path)
	node_chosen.emit(path,node)
