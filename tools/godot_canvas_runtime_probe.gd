extends SceneTree


func _initialize() -> void:
	boot.call_deferred()


func boot() -> void:
	var scene: Node = (load("res://SceneOne.tscn") as PackedScene).instantiate()
	root.add_child(scene)
	await create_timer(0.25).timeout
	var runtime: Node = scene.get_node("AlIBlueprint")
	var sprite: AnimatedSprite2D = scene.get_node("Object/AlIVisual") as AnimatedSprite2D
	assert(runtime.get("binding_root") == scene)
	assert(runtime.get("initialized") and sprite.is_playing())
	assert(sprite.sprite_frames.get_frame_count(sprite.animation) == 2)
	var receipt: FileAccess = FileAccess.open("res://canvas-runtime-proof.json", FileAccess.WRITE)
	receipt.store_string("{\"scene_owns_graph\":true,\"animation_started\":true}")
	receipt.close()
	quit()
