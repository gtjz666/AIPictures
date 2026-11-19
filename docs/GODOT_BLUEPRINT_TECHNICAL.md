# AlI Blueprint 0.5 技术文档（2D）

2026年11月18日 · Godot 4.6 stable验证 · 游戏运行API 6。

本版按完整需求实现适用的2D范围，分阶段仅表示实施顺序。Camera3D、Sprite3D、Billboard、2.5D与3D预览按用户要求暂缓。Vector3仅作为可传递、保存的数据类型。新增30类游戏模块，合计71类；角色由10类扩展至13类。模块是可组合能力，不代表71套完整玩法。

操作入口和教程见[使用步骤与验收范围](BLUEPRINT_05_PLAN.md)，全部端口、字段、默认值与范围见[模块手册](GODOT_BLUEPRINT_CATALOG.md)。素材生成保持手写单一提示词，蓝图执行不调用语言助手、自动分析或AI推理。

## 架构与责任

| 层／文件 | 职责 |
| --- | --- |
| game_model／game_registry／extended_registry | 原有模块、扩展模块的声明、字段、动态端口、升级与验证 |
| blueprint_types／blueprint_access | 共同类型、JSON编码、场景内节点寻址、白名单属性／方法 |
| game_library／subgraph_library | 旧子图展开、新参数子图编译冻结、签名、递归检查 |
| game_window／blueprint_window | 两个原生Window＋GraphEdit工作台，检查器、撤销、搜索、收藏与复制 |
| resource_slot／node_slot／resource_link | 原生拖放、类型检查、UID与路径、场景节点选择 |
| game_runtime／game_program | 保留的同步事件队列、数据求值、FSM、生命值与旧游戏行为 |
| blueprint_task／game_tasks | 统一任务生命周期、真实等待、串并行、取消、超时 |
| game_animations／animation_binding | Tween、AnimationPlayer、SpriteFrames统一适配；按钮、菜单、音频与预览复用 |
| game_features／game_widgets | 通用UI、属性、类型化事件及原生按钮，不复制物理／UI引擎 |
| game_world_tools | Camera2D、Sprite2D／Parallax2D、TileMapLayer与SceneObject |
| framework_services | 框架组合入口、生命周期、全局变量、注册数据，不把全部工作塞入主运行器 |
| framework_input／storage／scenes | InputMap、独立设置与多槽存档、线程预加载与场景转场 |
| framework_builder／menu／player | 创建原生可编辑模板、实际菜单操作与基础控制器 |
| asset_import／asset_import_wizard／tile_picker | 图片序列、Sprite Sheet、Animation轨道与TileSet导入／瓦片选择 |

游戏场景带私有运行模块目录，资源仍引用项目内文件。运行不依赖编辑器窗口或插件启用状态。框架服务挂在SceneTree根下，按配置key复用；子图只借用宿主服务，不建立第二套游戏或混音器。事件总线通过SceneTree分组共享，因此不同自含脚本副本仍能通信。

## 文件与兼容

游戏、角色图仍为version=1，字段为nodes、edges、params和position。新增字段由upgrade补默认值，旧端口编号不变。游戏保存原图game_blueprint、展开图compiled_blueprint和compiled_signature；修改子图源后必须重新编译应用，运行不偷偷读取新子图。

旧自含游戏API低于6时，工作台可以读原图，但拒绝直接应用新版功能。请创建新名称场景升级。原场景、旧运行副本和素材不覆盖。新建框架只接受不存在的res://目录；默认不更改项目启动场景。用户明确勾选后才保存main_scene设置。

资源路径继续存params；可选resources字段记录path／uid。UID可定位移动资源，手动改路径优先；身份冲突会拒绝，缺少UID则兼容路径。重导入使用缓存替换刷新。运行资源需随项目导出；发行时建议导出全部所需资源，动态JSON路径不一定被Godot依赖扫描发现。此次不声称已验证各平台发行包。

## 场景画布、函数作用域与动画轴

新画布对应一个 `.tscn`，蓝图和编译结果保存在场景内的 `AlIBlueprint` 节点。普通对象保有原脚本，模块使用场景相对路径找到目标。「应用到场景」可撤销，新增的精灵节点和看片段资源一起保存。旧框架场景保留自己的运行副本。

函数用可编译子图表示。局部函数放在带场景作用域的目录，全局函数放在 `res://blueprints/global`。构建时校验其可见范围，全局函数无法引用局部函数。修改后，调用方重新应用即可使用新编译结果。

AlI 的动画 ZIP 包含顺序 PNG 与 `animation.json`。在 Godot 动画轴调整后保存为项内 `SpriteFrames`，再由通用动画模块通过执行线播放。查看[场景蓝图教程](GODOT_SCENE_BLUEPRINT_GUIDE.md)。

## 类型、属性与事件

支持bool、number、text、Vector2、Vector3数据、Color、Node、Resource、Array、Dictionary。数据线要求同类型，每个数据入口最多一个来源；执行和事件端口保持0类型，显示颜色区分。数值、JSON和资源类型在编辑／编译／运行边界验证。更换类型会为不兼容的JSON初值提供相应类型默认值。

JSON示例：Vector2为[100,200]，Vector3为[1,2,3]，颜色为"ff8800ff"，节点为"Player/Visual"，资源为"res://art/player.png"。null使用相应默认值。Node必须位于当前游戏／角色根下，不接受绝对路径、上级跳转或任意对象实例化。引用失效后重新获取。

属性适配器只允许支持的原生属性，如位置、缩放、颜色、尺寸、文字、图片、数值、交互状态、速度、相机与地图属性，以及显式保存的hp／health／facing／dead；还检查目标实际属性与资源基类。支持position:x、modulate:a等适用子分量。受支持方法限show／hide／grab_focus等列出的原生方法，自定义逻辑通过项目脚本接口扩展。

event_send／event_receive使用命名事件与类型化参数：game隔离本游戏，role定位指定角色，project按框架key跨场景。角色send_event／receive_event使用同一总线。参数随事件链保存，避免延迟回调读到后来事件的数据。订阅使用弱引用，场景退出退订。事件队列每帧有预算，避免自发消息无限增长。

FSM保留进入、离开、当前／上一个状态和转换约束。可以将执行出口连接event_send、动画、相机、场景或输入逻辑；没有强制加入完整行为树。

## 可等待执行与取消

任务句柄只有running→completed／cancelled／failed一次终态，统一清理回调、子任务和settled信号。有限动画、等待、相机过渡、音频等待与子图都可被编排。失败输出与取消输出独立；没有连接它们不会伪装成功。

task_group可配置1–4分支。串行等待前一分支的完整下游结束；并行等待全部分支结束。组可以嵌套。旧Sequence仍在同次事件立即依次发出两路，不等待，避免改变旧图行为。wait=false表示启动后继续，持续动作需显式停止端口；退出场景仍统一取消。

重复入口可替换旧任务或忽略重复；同一对象属性可替换或拒绝新动画。删除目标导致失败；场景退出／重开清理旧任务。无限循环且等待结束会拒绝；不等待的无限动画需用户停止。串并行和子图具有超时。数据递归64层、每次事件512步、异步入口128、组256、等待1024、同时动画256，防止无限累积；执行记录最多256条。

游戏暂停冻结世界任务；ui=true的任务、按钮反馈和菜单可继续。框架GameManager暂停使用SceneTree.paused，旧session暂停仍保留局部语义。服务能在暂停时接收恢复与快速存取。场景切换一旦提交，转场任务保留到新场景淡入结束，避免旧场景退出取消新转场。

## 动画、按钮与预览

通用动画包括倍率缩放、相对／绝对位置、RGBA、指定起点、秒数、延迟、Transition／Ease、循环、反向、往返、速度、恢复、冲突策略。Animation／AnimationLibrary可加载片段，或直接选择场景中的AnimationPlayer；资源和片段列表与目标绑定。轨道目标必须有效，可用remap JSON映射旧节点路径，retarget把适用轨道绑定到目标本身。

运行创建动画／动画库副本，不改源文件；临时库在结束清理，按restore决定是否恢复属性和原播放状态。SpriteFrames复制后使用统一binding播放，选择片段、循环、反向和完成信号；动画资源没有帧会失败。一般属性动画只针对适用Control／Node2D，3D轨道不属于当前范围。

Button／TextureButton使用Godot原生四状态和五事件，悬停／点击音频接现有UI总线。effects_enabled默认关闭兼容旧图，可启用1.1悬停／0.95按下等反馈和点击Animation。模板菜单默认开启，可编辑或关闭。Container中的位置／缩放使用可恢复包装，避免父容器每帧重排抵消动效；结束场景时恢复父子层级和布局。

动画／Camera2D节点提供播放、暂停和停止复位的独立窗口。只复制原生可视节点与资源，不实例化用户脚本，原场景不变；预览仅执行白名单属性轨道，方法／音频／其他轨道会拒绝并提示。一般资源预览台仍提供独立色块预览；它不是完整场景动画编辑器。

## UI、地图与相机

ui_control创建或绑定Button、TextureButton、Label、RichTextLabel、TextureRect、Panel、PanelContainer、ProgressBar、HSlider、CheckBox、LineEdit、Control。复用属性读写实现显示、文字、图片、RGBA、透明度、尺寸、位置、数值与禁用／编辑状态。ui_event监听原生信号，最多四参数取首个，无参数提供所选类型默认值；也可监听场景物体信号。

背景使用Sprite2D／Parallax2D，支持尺寸、缩放、位置、旋转、透明度、层级、平铺、重复、自动滚动和多层。切换图片重复执行同一模块；通用动画对其节点操作。SceneObject使用图片、SpriteFrames或PackedScene，支持创建、变换、显示隐藏、播放动画及可选矩形StaticBody2D碰撞。绑定对象不能被删除端口误删，删除只针对该模块创建对象。

TileMapLayer可绑定现有图层或自动创建；TileSet含碰撞与地形配置，模块不另造物理引擎。支持源／图集／替代瓦片选择、放置替换、删除、区域填充清除、清空、读取、世界↔格子转换、地形连接、多层、层级、启停和碰撞开关。大区域每帧1024格批处理，取消保留已应用的部分，并记录差量。地形连接也记录受影响邻格。复杂地图使用原生TileMap／TileSet编辑器；蓝图提供入口。

图集向导支持格宽高、行列反算、边距、间距、选择和预览；不会自动猜测地形或碰撞。动画导入支持自然顺序图片、手动上下移、反序、Sprite Sheet切片、帧率与循环，默认SpriteFrames；显式勾选才输出Sprite2D.texture的Animation轨道。单张PNG不会被当作完整动画。

Camera2D支持移动、跟随、缩放、旋转、震动、当前相机切换、偏移、边界与平滑，提供平台／俯视／即时跟随参数预设。有限过渡走统一任务与终态输出；持续跟随在配置完成后输出完成，显式停止跟随。震动结束恢复原offset；相机预览同样隔离原场景。

## 参数化子图

旧flow_module/version1继续编译展开，变量／FSM名称按调用隔离。新增parameter_module/version2，module_input声明命名参数与默认值，module_output写入命名返回值。调用节点输入字典，完成后输出返回字典，可连接collection读取结果。

保存所选子图时须恰好一个外部执行入口和出口，跨边界数据线需把相应数据节点一起选入。包含module_input／output时自动保存v2。调用创建局部解释器，局部变量和返回值不泄漏；共享宿主服务、对象与全局变量。有限异步体完成且到达指定出口后才返回，缺返回／错误类型／超时失败。冻结时禁止递归，v2最多8层／64次调用，旧展开最多4层／64次；不在子图中放常驻事件源或按钮。

## 输入、音频与游戏服务

InputMap预设MoveLeft／Right／Up／Down（WASD和方向）、Jump（Space）、Run（Shift）、Interact（E）、Attack（鼠标左键／J）、Pause／Cancel（Esc）、Inventory（Tab）、Confirm（Enter）、QuickSave／Load（F5／F9）。已有项目动作不覆盖；支持多键、鼠标、按下释放按住、捕获、冲突拒绝／共享／抢占、重置和保存。角色按键可选择InputMap，旧物理键兼容。输入文本时屏蔽游戏按键；模板攻击／跳跃使用未被UI消费的事件。手柄可继续通过原生InputMap扩展，改键JSON目前只持久化键盘和鼠标。

音频复用现有私有Master／BGM／SFX／UI总线，提供播放停止、暂停恢复、循环、音量、完成、淡入淡出和位置声音。菜单没有游戏实例时使用单独播放器按设置计算音量，不新建冲突总线；进游戏后使用该游戏的UI总线。声音池与任务有边界，退出停止。

框架生命周期与单局session分工：整款游戏负责主菜单、开始、暂停恢复、结束、重开、退出；单局仍负责跑酷、分数等。SceneManager线程预加载、切换、重载、进入退出与淡入淡出，缓存PackedScene但不保留旧场景实例。

设置使用独立ConfigFile，管理四组音量、分辨率、窗口／全屏／无边框、键位、默认重置；运行修改即保存，下次恢复，不随存档回退。

## 存档与模板

存档在user://ali_framework_<key>/slot_N.json，0快速、1–20普通槽；默认菜单显示1–3槽，蓝图可访问全部。记录版本1、时间、校验和，临时文件＋备份提交；损坏、类型／版本不符会失败并保留文件，删除仅限当前框架槽。设置独立文件。

保存当前场景、配置变量／全局变量、指定角色位置与白名单属性、用户注册数据、FSM／生命／计时计分，以及初始地图上的运行差量。对象引用编码为相对路径，资源为项目路径；任意RefCounted／Thread／运行对象、内存资源与超过16层嵌套不直接保存。槽位限16MB。不是整个SceneTree快照。

读取先恢复场景，等运行器／地图就绪，再验证并恢复数据；角色缺失、资源变化、地图瓦片失效会报错。需要稍后由项目逻辑创建的对象，应由用户注册数据在loaded事件后重建，不自动序列化所有场景实例。

向导创建空白、基础移动、平台跳跃、跑酷四种2D框架。六个原生可编辑场景为MainMenu、Game、PauseMenu、SettingsMenu、SaveLoadMenu、GameOver；Game实例引用暂停／结束场景文件，设置／存取按需打开，编辑各文件会影响实际游戏。菜单动作、默认动画、音量改键、存取、返回与退出均连接实际服务。基础控制器和示例素材是代码占位，用户可替换或扩展。

## 调试、验证与边界

游戏工作台运行高亮每0.5秒读取匹配原图签名的调试快照，显示运行、完成、取消、失败；执行记录最多256条，点击可定位源模块。发行版不写调试文件。类型错误连接会拒绝并提示，JSON应用、资源更换、模块组粘贴和多选移动可撤销。角色工作台也支持搜索、收藏、复制与多选移动；相同角色动作只能声明一次，粘贴重复动作会拒绝并说明。

原生验证入口tools.verify_blueprint2d覆盖任务、地图、服务、子图、四框架、UI／角色通信、编辑器与预览；另保留原跑酷、程序图、角色、资源与按钮回归。具体证据与限制见使用步骤。没有声称自动AI素材精度、完整UE蓝图／NodeCanvas行为树、商业游戏全部系统或发行平台验证；完整背包、装备、多人网络等不在原0.5适用范围内。

## 公开设计参考

参考其通用思想，未复制或打包第三方插件：[UE执行与数据流](https://dev.epicgames.com/documentation/en-us/unreal-engine/basic-scripting-with-blueprints-in-unreal-engine)、[UE流程控制](https://dev.epicgames.com/documentation/en-us/unreal-engine/flow-control-in-unreal-engine)、[NodeCanvas黑板](https://nodecanvas.paradoxnotion.com/documentation/?section=the-blackboard)、[NodeCanvas状态机](https://nodecanvas.paradoxnotion.com/documentation/?section=fsm-node-reference)、[Godot InputMap](https://docs.godotengine.org/en/stable/classes/class_inputmap.html)、[Godot TileMapLayer](https://docs.godotengine.org/en/stable/classes/class_tilemaplayer.html)、[Godot Tween](https://docs.godotengine.org/en/stable/classes/class_tween.html)。实际接口以本机4.6原生验收为准。
