extends RefCounted
## Original tiny placeholder assets, not AI output or Google's dinosaur artwork.
static var sounds: Dictionary = {}


static func frames() -> SpriteFrames:
	var result: SpriteFrames = SpriteFrames.new()
	result.remove_animation(&"default")
	for clip: String in ["walk_right", "jump_right", "death_right"]:
		result.add_animation(clip)
		result.set_animation_speed(clip, 10.0 if clip == "walk_right" else 6.0)
		result.set_animation_loop(clip, clip == "walk_right")
		for frame: int in range(3 if clip == "death_right" else 2):
			var image: Image = Image.create(32, 32, false, Image.FORMAT_RGBA8)
			var ink: Color = Color("263d47") if clip != "death_right" else Color("ba5460")
			image.fill_rect(Rect2i(13, 3, 14, 10), ink)
			image.fill_rect(Rect2i(10, 11, 12, 13), ink)
			image.fill_rect(Rect2i(4, 15, 10, 6), ink)
			image.fill_rect(Rect2i(2, 12, 4, 5), ink)
			image.fill_rect(Rect2i(19, 15, 7, 3), ink)
			image.fill_rect(Rect2i(13, 23, 4, 7 if frame % 2 == 0 else 9), ink)
			image.fill_rect(Rect2i(21, 23, 4, 9 if frame % 2 == 0 else 7), ink)
			image.fill_rect(Rect2i(23, 5, 2, 2), Color.WHITE)
			image.fill_rect(Rect2i(20, 11, 8, 2), Color("92c5bf"))
			if clip == "death_right":
				image.fill_rect(Rect2i(22, 4, 4, 4), Color("ffe8a6") if frame % 2 == 0 else ink)
			result.add_frame(clip, ImageTexture.create_from_image(image))
	return result


static func sound(kind: String) -> AudioStreamWAV:
	if kind == "none":
		return null
	if sounds.has(kind):
		return sounds[kind] as AudioStreamWAV
	var rate: int = 22050
	var duration: float = 8.0 if kind == "music" else 0.35 if kind == "death" else 0.15 if kind == "jump" else 0.055
	var count: int = int(rate * duration)
	var bytes: PackedByteArray = PackedByteArray()
	bytes.resize(count * 2)
	var melody: Array[float] = [523.25, 659.25, 783.99, 659.25, 440.0, 523.25, 659.25, 523.25, 349.23, 440.0, 523.25, 440.0, 392.0, 493.88, 587.33, 493.88]
	for index: int in range(count):
		var time: float = float(index) / rate
		var value: float = 0.0
		if kind == "music":
			var beat: int = int(time * 2.0) % melody.size()
			var envelope: float = sin(PI * fmod(time, 0.5) / 0.5)
			value = sin(TAU * melody[beat] * time) * envelope * 0.16
			value += sin(TAU * melody[int(floor(float(beat) / 4.0)) * 4] * 0.25 * time) * 0.08 * sin(PI * fmod(time, 2.0) / 2.0)
		else:
			var phase: float = time / duration
			var frequency: float = 130.0 if kind == "step" else 780.0 if kind == "click" else 500.0 + phase * 450.0 if kind == "jump" else 400.0 - phase * 320.0
			value = sin(TAU * frequency * time) * (1.0 - phase) * 0.28
		var sample: int = clampi(int(value * 32767.0), -32767, 32767)
		bytes[index * 2] = sample & 255
		bytes[index * 2 + 1] = (sample >> 8) & 255
	var stream: AudioStreamWAV = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = rate
	stream.data = bytes
	sounds[kind] = stream
	return stream
