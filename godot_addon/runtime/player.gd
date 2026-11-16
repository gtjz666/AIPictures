# Adapted from the Godot skill's typed player_topdown_2d template.
# Self-contained generated CharacterBody2D; no autoloads or project input changes.
extends CharacterBody2D

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
    if platformer:
        motion_mode = CharacterBody2D.MOTION_MODE_GROUNDED


func play_action(action: String) -> bool:
    var clip: String = action + "_" + facing
    if not sprite.sprite_frames.has_animation(clip):
        clip = action
    if not sprite.sprite_frames.has_animation(clip):
        return false
    sprite.play(clip)
    if action in ["attack", "hurt", "death"]:
        action_time = float(sprite.sprite_frames.get_frame_count(clip)) / sprite.sprite_frames.get_animation_speed(clip)
    return true


func take_damage() -> void:
    damaged.emit()
    play_action("hurt")


func die() -> void:
    dead = true
    velocity = Vector2.ZERO
    footsteps.stop()
    died.emit()
    play_action("death")


func _physics_process(delta: float) -> void:
    if dead:
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
    var target: Vector2 = direction * speed * (run_multiplier if running else 1.0)
    if platformer:
        velocity.x = move_toward(velocity.x, target.x, (acceleration if moving else friction) * delta)
        velocity.y += gravity * delta
        if jumping and not jump_held and is_on_floor():
            velocity.y = jump_velocity
            jump_requested.emit()
    else:
        velocity = velocity.move_toward(target, (acceleration if moving else friction) * delta)
    if moving:
        if four_way:
            facing = ("right" if direction.x > 0.0 else "left") if absf(direction.x) > absf(direction.y) else ("down" if direction.y > 0.0 else "up")
        else:
            facing = "right"
            sprite.flip_h = direction.x < 0.0
    if attacking and not attack_held:
        attack_requested.emit()
        play_action("attack")
    action_time = maxf(0.0, action_time - delta)
    if action_time <= 0.0:
        if platformer and not is_on_floor() and play_action("jump"):
            pass
        elif moving:
            if not running or not play_action("run"):
                play_action("walk")
        elif not play_action("idle"):
            sprite.stop()
            sprite.frame = 0
    if not moving or (platformer and not is_on_floor()):
        footsteps.stop()
        sound_elapsed = footstep_interval
    move_and_slide()
    sound_elapsed += delta
    if moving and (not platformer or is_on_floor()) and footsteps.stream != null and not footsteps.playing and sound_elapsed >= footstep_interval:
        footsteps.play()
        sound_elapsed = 0.0
    attack_held = attacking
    jump_held = jumping
