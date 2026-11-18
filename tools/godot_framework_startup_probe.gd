extends Node
## Autoloaded in an isolated proof project while Godot starts a real scene.


func _ready() -> void:
	run.call_deferred()


func wait_frames(count: int) -> void:
	for index: int in range(count):
		OS.delay_msec(4)
		await get_tree().process_frame


func run() -> void:
	await wait_frames(30)
	var scene: Node = get_tree().current_scene
	assert(scene != null,"真实启动场景不存在")
	var initial_name: String = scene.scene_file_path.get_file().get_basename()
	var service: Node
	if initial_name == "MainMenu":
		service = scene.get("service") as Node
		assert(service != null and service.get("bus") != null,"主菜单服务未初始化")
		(scene.find_child("SettingsButton",true,false) as Button).pressed.emit()
		await wait_frames(50)
		var overlays: Array = scene.get("transient")
		assert(overlays.size() == 1 and overlays[0].visible,"设置界面未打开")
		(overlays[0].find_child("BackButton",true,false) as Button).pressed.emit()
		await wait_frames(60)
		(scene.find_child("StartButton",true,false) as Button).pressed.emit()
		await wait_frames(120)
	else:
		assert(initial_name == "Game","意外的启动场景")
		service = scene.get("services") as Node
	var game: Node = get_tree().current_scene
	assert(game != null and game.get("initialized") == true,"游戏初始化失败")
	assert(service != null and service.call("current_game") == game,"游戏服务未关联")
	var preset: String = str(game.get("framework").get("preset"))
	if preset == "platformer":
		var player: Node = game.get_node("Player")
		var subscribed: bool = false
		for row: Dictionary in service.get("bus").get("listeners"):
			if row["owner"].get_ref() == player and row["event"] == "restarted": subscribed = true
		assert(subscribed,"平台角色未绑定重开事件")
	service.call("lifecycle","pause")
	await wait_frames(20)
	assert(get_tree().paused and game.get_node("Menus/PauseMenu").visible,"暂停界面未响应")
	service.call("lifecycle","resume")
	await wait_frames(20)
	assert(not get_tree().paused,"游戏未恢复")
	service.call("lifecycle","end")
	await wait_frames(20)
	assert(game.get_node("Menus/GameOver").visible,"死亡界面未响应")
	var path: String = "res://startup_" + preset + "_" + initial_name + ".json"
	var file: FileAccess = FileAccess.open(path,FileAccess.WRITE)
	assert(file != null,"无法保存验收结果")
	file.store_string(JSON.stringify({"preset":preset,"initial_scene":initial_name,"ready":true,"pause":true,"gameover":true}))
	file.close()
	OS.delay_msec(250)
	get_tree().quit(0)
