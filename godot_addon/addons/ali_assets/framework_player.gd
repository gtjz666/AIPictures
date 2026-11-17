extends CharacterBody2D
## Editable native template controller; artwork is an original placeholder.
const Binding: GDScript = preload("animation_binding.gd")
signal jumped
signal landed
signal attacked
signal interacted
@export_enum("topdown","platformer") var mode: String = "topdown"
@export var speed: float = 220.0
@export var acceleration: float = 1800.0
@export var gravity: float = 1200.0
@export var jump_velocity: float = -460.0
@export var run_multiplier: float = 1.6
@export var hp: float = 100.0
var facing: Vector2 = Vector2.DOWN
var coyote: float = 0.0
var buffered: float = 0.0
var floor_before: bool = false
var start_position: Vector2
var game: Node
var input_pulses: Dictionary = {}


func _ready() -> void:
	start_position = position
	game = get_parent()
	bind_services.call_deferred()


func bind_services() -> void:
	if game.has_method("settings"):
		var bus: Node = game.get("services").get("bus") as Node
		bus.call("subscribe",self,"project:"+str(game.get("services").get("key")),"restarted",func(_data: Variant) -> void: position = start_position; velocity = Vector2.ZERO; hp = 100.0)


func _physics_process(delta: float) -> void:
	if game != null and game.get("state") != "running": return
	if not actions_ready(): return
	var focus: Control = get_viewport().gui_get_focus_owner()
	var blocked: bool = focus is LineEdit or focus is TextEdit
	var direction: Vector2 = Vector2.ZERO if blocked else Input.get_vector("MoveLeft","MoveRight","MoveUp","MoveDown")
	var pace: float = speed * (run_multiplier if not blocked and Input.is_action_pressed("Run") else 1.0)
	if mode == "platformer":
		coyote = 0.12 if is_on_floor() else coyote - delta
		buffered = 0.12 if not blocked and input_pulses.has("Jump") else buffered - delta
		if not is_on_floor(): velocity.y += gravity * delta
		if coyote > 0.0 and buffered > 0.0:
			velocity.y = jump_velocity
			coyote = 0.0
			buffered = 0.0
			jumped.emit()
		if not blocked and Input.is_action_just_released("Jump") and velocity.y < 0.0: velocity.y *= 0.45
		velocity.x = move_toward(velocity.x,direction.x*pace,acceleration*delta)
	else: velocity = velocity.move_toward(direction*pace,acceleration*delta)
	if direction.length_squared() > 0.0: facing = direction
	move_and_slide()
	if mode == "platformer":
		if is_on_floor() and not floor_before: landed.emit()
		floor_before = is_on_floor()
		if position.y > 1000.0: game.get("services").call("lifecycle","end")
	var visual: AnimatedSprite2D = get_node_or_null("Visual") as AnimatedSprite2D
	if visual != null:
		visual.flip_h = facing.x < 0.0
		var clip: String = "jump_right" if mode == "platformer" and not is_on_floor() else "walk_right"
		Binding.play(visual,clip,1.0,false,false)
		if direction.is_zero_approx() and (mode != "platformer" or is_on_floor()): visual.pause()
	if not blocked and input_pulses.has("Attack"): attacked.emit()
	if not blocked and input_pulses.has("Interact"): interacted.emit()
	input_pulses.clear()


func actions_ready() -> bool:
	return InputMap.has_action("MoveLeft") and InputMap.has_action("MoveRight") and InputMap.has_action("MoveUp") and InputMap.has_action("MoveDown") and InputMap.has_action("Run") and InputMap.has_action("Jump") and InputMap.has_action("Attack") and InputMap.has_action("Interact")


func _unhandled_input(event: InputEvent) -> void:
	if game == null or game.get("state") != "running" or not event.is_pressed() or event is InputEventKey and event.echo: return
	for action: String in ["Jump","Attack","Interact"]:
		if InputMap.has_action(action) and event.is_action(action): input_pulses[action] = true


func _exit_tree() -> void:
	if is_instance_valid(game) and game.get("services") != null: game.get("services").get("bus").call("unsubscribe",self)
