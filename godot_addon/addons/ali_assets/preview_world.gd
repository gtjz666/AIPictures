@tool
extends Node2D
const Animations: GDScript = preload("game_animations.gd")
const World: GDScript = preload("game_world_tools.gd")
var state: String = "running"
var animations: Node
var world_tools: Node
var game_blueprint: Dictionary = {"nodes":[]}


func _ready() -> void:
	animations = Animations.new()
	add_child(animations)
	animations.call("setup",self)
	world_tools = World.new()
	add_child(world_tools)
	world_tools.call("setup",self)
