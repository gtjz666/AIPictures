@tool
extends Button

var resource_path: String = ""


func _get_drag_data(_at_position: Vector2) -> Variant:
	if resource_path.is_empty():
		return null
	var label: Label = Label.new()
	label.text = text
	set_drag_preview(label)
	return asset_drag_data()


func asset_drag_data() -> Dictionary:
	return {"type": "files", "files": PackedStringArray([resource_path])}
