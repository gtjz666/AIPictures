@tool
extends RefCounted
## Shared SpriteFrames entry point for role, generic and legacy scene playback.


static func play(sprite: AnimatedSprite2D, clip: StringName, speed: float = 1.0, from_end: bool = false, restart: bool = false) -> bool:
	if not is_instance_valid(sprite) or sprite.sprite_frames == null or not sprite.sprite_frames.has_animation(clip) or sprite.sprite_frames.get_frame_count(clip) == 0: return false
	if restart: sprite.stop()
	sprite.play(clip,speed,from_end)
	return true
