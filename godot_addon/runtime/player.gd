# Adapted from the Godot skill's typed player_topdown_2d template.
# Self-contained generated CharacterBody2D; no autoloads or project input changes.
extends CharacterBody2D
const BlueprintRuntime: GDScript = preload("blueprint_runtime.gd")
@export var blueprint: Dictionary = {}
signal action_requested(action: String)
var blueprint_runtime: RefCounted
var movement_action: String = "move_right"
var is_running: bool = false

@export var speed: float = 180.0
@export var acceleration: float = 1400.0
@export var friction: float = 1600.0
@export var four_way: bool = false
@export var input_left: StringName = &"ui_left"
@export var input_right: StringName = &"ui_right"
@export var input_up: StringName = &"ui_up"
@export var input_down: StringName = &"ui_down"
@export var footstep_interval: float = 0.35
@onready var sprite: AnimatedSprite2D = $AnimatedSprite2D
@onready var footsteps: AudioStreamPlayer2D = $Footsteps
@export var platformer: bool = false
@export var gravity: float = 980.0
@export var jump_velocity: float = -380.0
@export var run_multiplier: float = 1.8
@export var use_project_actions: bool = false
@export var key_left: Key = KEY_A
@export var key_right: Key = KEY_D
@export var key_up: Key = KEY_W
@export var key_down: Key = KEY_S
@export var key_run: Key = KEY_SHIFT
@export var key_jump: Key = KEY_SPACE
@export var key_attack: Key = KEY_J
signal attack_requested
signal jump_requested
signal damaged
signal died
var facing: String = "right"
var sound_elapsed: float = 0.0
var action_time: float = 0.0
var attack_held: bool = false
var jump_held: bool = false
var dead: bool = false


func _ready() -> void:
    if not blueprint.is_empty():
        blueprint_runtime = BlueprintRuntime.new()
        if not blueprint_runtime.call("setup", blueprint, self, sprite):
            push_error("AlI角色蓝图：" + str(blueprint_runtime.get("error")))
            set_physics_process(false)
            return
        var settings: Dictionary = blueprint["settings"]
        platformer = settings["mode"] == "platformer"
        four_way = settings["mode"] == "four_way"
        speed = float(settings["speed"])
        run_multiplier = float(settings["run_multiplier"])
        gravity = float(settings["gravity"])
        jump_velocity = float(settings["jump_velocity"])
        footsteps.stop()
    if platformer:
        motion_mode = CharacterBody2D.MOTION_MODE_GROUNDED
    if blueprint_runtime != null:
        blueprint_runtime.call("emit_event", "ready")


func play_action(action: String, restart: bool = false) -> bool:
    if blueprint_runtime != null:
        var routed: String = movement_action if action == "walk" else action
        if not blueprint_runtime.call("play", routed, restart):
            return false
        if action not in ["idle", "walk", "run", "jump", "fall", "climb"]:
            action_time = animation_duration()
        return true
    var clip: String = action + "_" + facing
    if not sprite.sprite_frames.has_animation(clip):
        clip = action
    if not sprite.sprite_frames.has_animation(clip):
        return false
    sprite.play(clip)
    if action in ["attack", "hurt", "death"]:
        action_time = float(sprite.sprite_frames.get_frame_count(clip)) / sprite.sprite_frames.get_animation_speed(clip)
    return true


func animation_duration() -> float:
    var total: float = 0.0
    for index: int in range(sprite.sprite_frames.get_frame_count(sprite.animation)):
        total += sprite.sprite_frames.get_frame_duration(sprite.animation, index)
    return total / maxf(0.01, sprite.sprite_frames.get_animation_speed(sprite.animation))


func take_damage() -> void:
    damaged.emit()
    if blueprint_runtime != null:
        blueprint_runtime.call("emit_event", "hurt")
    play_action("hurt", true)


func die() -> void:
    dead = true
    velocity = Vector2.ZERO
    footsteps.stop()
    if blueprint_runtime != null:
        blueprint_runtime.call("stop")
    died.emit()
    if blueprint_runtime != null:
        blueprint_runtime.call("emit_event", "death")
    play_action("death", true)


func _physics_process(delta: float) -> void:
    var blocked: bool = get_viewport().gui_get_focus_owner() is LineEdit or get_viewport().gui_get_focus_owner() is TextEdit
    if dead:
        if blueprint_runtime != null:
            blueprint_runtime.call("input_state", delta)
            blueprint_runtime.call("tick", delta)
        return
    var direction: Vector2 = Input.get_vector(input_left, input_right, input_up, input_down) if use_project_actions else Vector2(
        float(Input.is_physical_key_pressed(key_right)) - float(Input.is_physical_key_pressed(key_left)),
        float(Input.is_physical_key_pressed(key_down)) - float(Input.is_physical_key_pressed(key_up)))
    if not four_way:
        direction.y = 0.0
    direction = direction.normalized()
    var moving: bool = direction.length_squared() > 0.0
    var running: bool = Input.is_physical_key_pressed(key_run)
    var jumping: bool = Input.is_physical_key_pressed(key_jump)
    var attacking: bool = Input.is_physical_key_pressed(key_attack)
    if blocked:
        direction = Vector2.ZERO
        moving = false
        running = false
        jumping = false
        attacking = false
    var triggered: Array = []
    if blueprint_runtime != null:
        var state: Dictionary = blueprint_runtime.call("input_state", delta)
        direction = state["direction"]
        if not four_way:
            direction.y = 0.0
        direction = direction.normalized()
        moving = direction.length_squared() > 0.0
        running = state["active"].has("run")
        jumping = state["active"].has("jump")
        attacking = state["active"].has("attack")
        triggered = state["pressed"]
    is_running = running
    var target: Vector2 = direction * speed * (run_multiplier if running else 1.0)
    if platformer:
        velocity.x = move_toward(velocity.x, target.x, (acceleration if moving else friction) * delta)
        velocity.y += gravity * delta
        if jumping and not jump_held and is_on_floor():
            velocity.y = jump_velocity
            jump_requested.emit()
            play_action("jump", true)
    else:
        velocity = velocity.move_toward(target, (acceleration if moving else friction) * delta)
        if blueprint_runtime != null and jumping and not jump_held:
            jump_requested.emit()
            if play_action("jump", true):
                action_time = animation_duration()
    if moving:
        movement_action = "move_" + (("right" if direction.x > 0.0 else "left") if absf(direction.x) > absf(direction.y) else ("down" if direction.y > 0.0 else "up"))
        if four_way:
            facing = ("right" if direction.x > 0.0 else "left") if absf(direction.x) > absf(direction.y) else ("down" if direction.y > 0.0 else "up")
        else:
            facing = "right"
            sprite.flip_h = direction.x < 0.0
    if attacking and not attack_held:
        attack_requested.emit()
        play_action("attack", true)
    for action: String in triggered:
        action_requested.emit(action)
        if action not in ["move_left", "move_right", "move_up", "move_down", "run", "jump", "attack", "idle", "walk"]:
            if action == "death":
                die()
            elif action == "hurt":
                damaged.emit()
                play_action("hurt", true)
            else:
                play_action(action, true)
    action_time = maxf(0.0, action_time - delta)
    if action_time <= 0.0:
        if platformer and not is_on_floor() and play_action("jump"):
            pass
        elif moving:
            if not running or not play_action("run"):
                play_action("walk")
        elif not play_action("idle"):
            if blueprint_runtime != null:
                blueprint_runtime.call("stop")
            sprite.stop()
            sprite.frame = 0
    if not moving or (platformer and not is_on_floor()):
        footsteps.stop()
        sound_elapsed = footstep_interval
    move_and_slide()
    sound_elapsed += delta
    if blueprint_runtime != null:
        blueprint_runtime.call("tick", delta)
    elif moving and (not platformer or is_on_floor()) and footsteps.stream != null and not footsteps.playing and sound_elapsed >= footstep_interval:
        footsteps.play()
        sound_elapsed = 0.0
    attack_held = attacking
    jump_held = jumping


func set_blueprint_variable(variable: String, value: bool) -> void:
    if blueprint_runtime != null:
        var values: Dictionary = blueprint_runtime.get("variables")
        values[variable] = value


func _exit_tree() -> void:
    if blueprint_runtime != null:
        blueprint_runtime.call("dispose")
