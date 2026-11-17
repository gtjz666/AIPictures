@tool
extends Window
signal tile_selected(source: int, coords: Vector2i, alternative: int)


func _init() -> void:
	visible = false
	force_native = true


func present(tiles: TileSet) -> void:
	title = "AlI · 选择TileSet瓦片"
	size = Vector2i(700,480)
	close_requested.connect(queue_free)
	var grid: ItemList = ItemList.new()
	grid.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	grid.max_columns = 0
	grid.fixed_column_width = 110
	grid.fixed_icon_size = Vector2i(72,72)
	grid.icon_mode = ItemList.ICON_MODE_TOP
	add_child(grid)
	for source_index: int in range(tiles.get_source_count()):
		var id: int = tiles.get_source_id(source_index)
		var atlas: TileSetAtlasSource = tiles.get_source(id) as TileSetAtlasSource
		if atlas == null: continue
		for index: int in range(atlas.get_tiles_count()):
			var coords: Vector2i = atlas.get_tile_id(index)
			var texture: AtlasTexture = AtlasTexture.new()
			texture.atlas = atlas.texture
			texture.region = Rect2(atlas.get_tile_texture_region(coords))
			for alternative_index: int in range(atlas.get_alternative_tiles_count(coords)):
				var alternative: int = atlas.get_alternative_tile_id(coords,alternative_index)
				var item: int = grid.add_item(str(id)+" · "+str(coords)+" · "+str(alternative),texture)
				grid.set_item_metadata(item,{"source":id,"coords":coords,"alternative":alternative})
	grid.item_activated.connect(func(index: int) -> void:
		var value: Dictionary = grid.get_item_metadata(index)
		tile_selected.emit(value["source"],value["coords"],value["alternative"])
		queue_free())
	popup_centered_clamped(Vector2i(700,480),0.8)
