extends Node
## Adapted from the skill audio pool: bounded voices, private buses, no autoload.
const Assets: GDScript = preload("game_assets.gd")
var game: Node2D
var params: Dictionary
var module_id: String
var players: Array[AudioStreamPlayer] = []
var next_voice: int = 0
var playing_loop: bool = false
var triggers: int = 0


func setup(controller: Node2D, id: String, settings: Dictionary, bus: StringName) -> void:
	game = controller
	module_id = id
	params = settings
	var stream: AudioStream = Assets.sound(str(params["demo"])) if str(params["path"]).is_empty() else load(str(params["path"])) as AudioStream
	if stream != null:
		stream = stream.duplicate() as AudioStream
		if stream is AudioStreamWAV:
			(stream as AudioStreamWAV).loop_mode = AudioStreamWAV.LOOP_DISABLED
		elif stream is AudioStreamOggVorbis:
			(stream as AudioStreamOggVorbis).loop = false
		elif stream is AudioStreamMP3:
			(stream as AudioStreamMP3).loop = false
	for index: int in range(1 if params["loop"] else int(params["voices"])):
		var player: AudioStreamPlayer = AudioStreamPlayer.new()
		player.stream = stream
		player.bus = bus
		player.volume_db = float(params["volume"])
		add_child(player)
		player.finished.connect(func() -> void:
			if playing_loop and game.get("state") == "running":
				player.play()
			else:
				game.call("emit_port", module_id, 0))
		players.append(player)


func command(port: int) -> void:
	match port:
		0:
			if players.is_empty() or players[0].stream == null:
				return
			playing_loop = bool(params["loop"])
			if playing_loop and players[0].playing:
				return
			var player: AudioStreamPlayer = players[next_voice]
			player.stream_paused = false
			player.play()
			triggers += 1
			next_voice = (next_voice + 1) % players.size()
		1:
			playing_loop = false
			for player: AudioStreamPlayer in players:
				player.stop()
		2: pause(true)
		3: pause(false)


func pause(value: bool) -> void:
	for player: AudioStreamPlayer in players:
		player.stream_paused = value
