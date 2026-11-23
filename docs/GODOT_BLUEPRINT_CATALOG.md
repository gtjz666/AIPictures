# AlI Blueprint 0.5 模块与参数手册

2026年11月18日 · Godot 4.6 · API 6 · 2D版。

原生注册表只读提取：73类游戏模块、13类角色模块、350项游戏字段。19项角色动作是动作模块内的选项。

先读[使用步骤](BLUEPRINT_05_PLAN.md)与[技术文档](GODOT_BLUEPRINT_TECHNICAL.md)。白色执行、橙色事件；绿色布尔、蓝色数字、粉色文字，其余类型使用不同数据色。事件口仍沿用执行端口编号，不破坏旧图。

## 游戏模块索引

| 模块 | 分类 | 用途 |
| --- | --- | --- |
| 游戏状态／计分（session） | 游戏与界面 | 游戏状态／计分：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 游戏按键（input） | 事件与输入 | 游戏按键：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 自动奔跑角色（runner） | 游戏与界面 | 自动奔跑角色：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 背景／地面滚动（world） | 游戏与界面 | 背景／地面滚动：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 障碍生成／碰撞（spawner） | 游戏与界面 | 障碍生成／碰撞：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 菜单／分数／设置UI（hud） | 游戏与界面 | 菜单／分数／设置UI：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 音频总线混音（mixer） | 游戏与界面 | 音频总线混音：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 画面比例（screen） | 游戏与界面 | 画面比例：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 播放声音（audio） | 游戏与界面 | 播放声音：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 计时器（timer） | 逻辑与状态 | 计时器：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 条件分支（branch） | 逻辑与状态 | 条件分支：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 顺序执行（sequence） | 逻辑与状态 | 兼容旧图：立即依次触发两个输出，不等待下游异步任务。需要等待请使用串行／并行任务。 |
| 延迟（delay） | 逻辑与状态 | 延迟：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 布尔变量（boolean） | 变量与数据 | 布尔变量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 自定义模块（custom） | 场景与玩法 | 自定义模块：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 界面按钮（button） | 游戏与界面 | 原生Button／TextureButton的四状态、声音和五事件。动效复用通用动画；Container中通过可恢复包装保持布局。 |
| 黑板变量（blackboard） | 变量与数据 | 声明场景／子图局部变量或框架全局变量。全局变量跨场景保留；重置开关明确控制是否重新初始化。 |
| 写入变量（set_variable） | 变量与数据 | 写入变量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 数字常量（number） | 变量与数据 | 数字常量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 文字常量（text） | 变量与数据 | 文字常量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 数字运算（math） | 变量与数据 | 数字运算：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 数字比较（compare） | 变量与数据 | 数字比较：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 布尔运算（logic） | 变量与数据 | 布尔运算：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 读取游戏数据（game_value） | 变量与数据 | 读取游戏数据：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 只执行一次（do_once） | 逻辑与状态 | 只执行一次：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 执行闸门（gate） | 逻辑与状态 | 执行闸门：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 交替执行（flip_flop） | 逻辑与状态 | 交替执行：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 冷却限制（cooldown） | 逻辑与状态 | 冷却限制：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 状态机（fsm） | 逻辑与状态 | 状态机：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 切换状态（set_state） | 逻辑与状态 | 切换状态：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 发送命名事件（event_emit） | 事件与输入 | 发送命名事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 接收命名事件（event_listener） | 事件与输入 | 接收命名事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 生命值（health） | 场景与玩法 | 生命值：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 生成场景实例（spawn_scene） | 场景与玩法 | 生成场景实例：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 场景节点操作（node_action） | 场景与玩法 | 场景节点操作：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 场景信号事件（signal_event） | 事件与输入 | 场景信号事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 调试记录（log） | 场景与玩法 | 调试记录：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 可复用子图（module） | 逻辑与状态 | 可复用子图：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 自定义按键事件（key_event） | 事件与输入 | 自定义按键事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 文字格式化（format_text） | 变量与数据 | 文字格式化：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 界面提示（ui_message） | 游戏与界面 | 界面提示：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 通用动画（animation） | 动画与异步 | 统一属性Tween、AnimationPlayer与SpriteFrames任务。完成、取消、失败分别连线；无限循环需关闭等待。停止恢复由恢复初始开关控制。 |
| 串行／并行任务（task_group） | 动画与异步 | 每个分支包含下游完整流程。串行等待前一分支真正结束；并行等待全部结束。旧顺序模块保持立即依次发出信号。 |
| 可等待延迟（wait_task） | 动画与异步 | 受游戏暂停控制的可取消延迟；UI开关允许暂停时继续。 |
| 通用UI操作（ui_control） | 通用UI | 创建或绑定原生控件，写入指定值。值类型必须与目标属性匹配；可用数据线动态输入。 |
| UI事件（ui_event） | 通用UI | 绑定原生节点信号。最多四参数时取第一参数；无参数发出所选类型默认值。目标可为场景物体或UI。 |
| 获取节点引用（node_ref） | 变量与数据 | 获取节点引用：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 读取属性（property_get） | 变量与数据 | 读取属性：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 修改属性（property_set） | 变量与数据 | 修改属性：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 受支持方法（method_call） | 变量与数据 | 受支持方法：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 获取资源引用（resource_ref） | 变量与数据 | 获取资源引用：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 类型化常量（typed_value） | 变量与数据 | 类型化常量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 数组／字典操作（collection） | 变量与数据 | 数组／字典操作：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 发送参数事件（event_send） | 事件与输入 | 发送带类型参数的命名事件；本游戏、指定角色或框架跨场景作用域。 |
| 接收参数事件（event_receive） | 事件与输入 | 订阅带参数事件；场景退出自动退订。接收类型需与发送端一致。 |
| 子图输入参数（module_input） | 变量与数据 | 定义子图命名输入与默认值；将值连到需要的数据口。 |
| 子图返回参数（module_output） | 变量与数据 | 定义命名返回值并执行返回。子图到达选定执行出口后，调用节点输出返回字典。 |
| 参数化子图（subgraph） | 动画与异步 | 带命名参数与返回字典的可等待子图，局部变量隔离。保存场景时编译冻结，源JSON可不随运行包。 |
| Camera2D控制（camera2d） | 地图与场景 | 相机移动、跟随、缩放、旋转、震动、切换与边界。有限过渡可串并行等待；持续跟随在配置完成后输出完成。 |
| 背景／视差（background） | 地图与场景 | 原生Sprite2D／Parallax2D，多层、尺寸、平铺与自动滚动。背景动画请连通用动画模块。 |
| TileMapLayer地图（tilemap） | 地图与场景 | 绑定或创建TileMapLayer。复杂地图、地形与碰撞在Godot原生编辑器配置；本模块修改格子并记录存档差量。大区域每帧批处理。 |
| 场景物体（scene_object） | 地图与场景 | 创建图片、SpriteFrames或PackedScene；绑定现有对象可显示、变换、播放动画。删除端口只删除此模块创建的对象。 |
| InputMap动作（input_action） | 事件与输入 | 读取Godot InputMap，输出按下、释放、按住与强度。输入框聚焦时默认屏蔽游戏输入。 |
| 运行时改键（input_bind） | 事件与输入 | 为动作绑定多个键或鼠标、捕获新键、处理冲突、恢复默认并写入独立设置文件。 |
| 音频渐变／位置声音（audio_fx） | 游戏服务 | 音频渐变／位置声音：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 游戏生命周期（game_service） | 游戏服务 | 初始化、开始、暂停、继续、结束、重开、返回菜单与退出。框架暂停冻结世界，UI任务可继续。 |
| 场景切换／转场（scene_service） | 游戏服务 | 切换或预加载场景。叠加界面可以独立编辑，打开时可暂停当前游戏，关闭后继续原局。 |
| 设置管理（settings_service） | 游戏服务 | 分辨率、窗口模式、四路音量和输入绑定独立持久化，不随存档回退。 |
| 存档管理（save_service） | 游戏服务 | 多槽存取；先恢复场景，再恢复注册变量、角色属性与地图差量。槽0为快速存档，设置单独保存。 |
| 注册存档数据（data_register） | 游戏服务 | 注册存档数据：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 游戏／场景事件（game_event） | 事件与输入 | 游戏／场景事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。 |
| 帧更新事件（frame_event） | 事件与输入 | 每个普通帧或物理帧触发一次，输出本次更新经过的秒数。 |
| 2D接触状态（body_contact） | 变量与数据 | 读取 CharacterBody2D 最近一次移动后的地面、墙壁或天花板接触状态。 |

## 全部游戏模块字段

端口从0编号。表中数据类型对应默认参数；改变value_type等参数后，端口随之变化。未连数据线时使用默认值。JSON默认null表示所选类型的默认值。资源需项目内res://路径，节点需相对游戏根节点路径。

### 游戏状态／计分（session）

游戏状态／计分：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 开始（执行）；1 游戏结束（执行）；2 重新开始（执行）；3 暂停／继续（执行）；4 加分（执行）

输出：0 开始时（执行）；1 结束时（执行）；2 重开时（执行）；3 暂停时（执行）；4 继续时（执行）；5 分数变化（执行）

此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| points_per_second／每秒分数 | number | 10.0 | 0～100 |
| obstacle_points／越过障碍加分 | number | 10.0 | 0～1000 |
| save_key／独立存档名称 | text | pixel_runner |  |

### 游戏按键（input）

游戏按键：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 跳跃键（执行）；1 开始键（执行）；2 重开键（执行）；3 暂停键（执行）

此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| jump／跳跃／开始键 | key | Space |  |
| pause／暂停键 | key | Escape |  |
| restart／重开键 | key | R |  |

### 自动奔跑角色（runner）

自动奔跑角色：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 开始／重置（执行）；1 跳跃（执行）；2 死亡（执行）；3 停止（执行）

输出：0 起跳时（执行）；1 落地时（执行）；2 死亡时（执行）；3 死亡动画结束（执行）；4 地面脚步（执行）

此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| frames／角色动画资源 | asset |  | frames |
| walk／行走动画名 | text | walk_right |  |
| jump／跳跃动画名 | text | jump_right |  |
| death／死亡动画名 | text | death_right |  |
| height／显示高度 | number | 84.0 | 16～300 |
| collision_width／碰撞宽度 | number | 38.0 | 4～200 |
| collision_height／碰撞高度 | number | 68.0 | 4～280 |
| gravity／重力 | number | 1600.0 | 300～4000 |
| jump_velocity／起跳速度 | number | -640.0 | -1500～-200 |
| step_interval／地面脚步间隔／秒 | number | 0.22 | 0.08～2 |

### 背景／地面滚动（world）

背景／地面滚动：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 开始／重置（执行）；1 停止（执行）

输出：无。

此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| background／背景贴图 | asset |  | image |
| ground／地面贴图 | asset |  | image |
| sky／背景颜色 | color | dceef0 |  |
| ground_color／地面颜色 | color | 183d45 |  |
| ground_ratio／地面高度位置 | number | 0.8 | 0.55～0.9 |
| parallax／背景滚动倍率 | number | 0.15 | 0～1 |

### 障碍生成／碰撞（spawner）

障碍生成／碰撞：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 开始／清空（执行）；1 停止（执行）

输出：0 碰到角色（执行）；1 越过障碍（执行）

此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| texture／障碍贴图 | asset |  | image |
| speed／初始滚动速度 | number | 300.0 | 80～800 |
| max_speed／最高速度 | number | 500.0 | 80～1000 |
| acceleration／每秒加速 | number | 3.0 | 0～30 |
| interval_min／最短生成间隔／秒 | number | 1.5 | 0.3～8 |
| interval_max／最长生成间隔／秒 | number | 2.4 | 0.3～10 |
| width／障碍宽度 | number | 36.0 | 10～160 |
| height／障碍高度 | number | 58.0 | 10～200 |
| fair_spacing／自动限制障碍高度与间距 | bool | 开 |  |

### 菜单／分数／设置UI（hud）

菜单／分数／设置UI：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 游戏画面（执行）；1 结束菜单（执行）；2 开始菜单（执行）；3 暂停菜单（执行）；4 更新分数（执行）；5 开关设置（执行）

输出：0 开始按钮（执行）；1 重开按钮（执行）；2 暂停按钮（执行）；3 跳跃按钮（执行）；4 按钮音效（执行）

此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| title／游戏标题 | text | PIXEL RUN |  |
| logo／标题图片 | asset |  | image |
| panel／面板贴图（九宫格） | asset |  | image |
| button／按钮普通贴图 | asset |  | image |
| hover／按钮悬停贴图 | asset |  | image |
| pressed／按钮按下贴图 | asset |  | image |
| touch_jump／显示触屏跳跃按钮 | bool | 开 |  |
| start_text／开始按钮文字 | text | START |  |
| retry_text／重开按钮文字 | text | RETRY |  |
| pause_text／暂停按钮文字 | text | PAUSE |  |
| resume_text／继续按钮文字 | text | RESUME |  |
| over_text／结束标题 | text | GAME OVER |  |
| jump_text／跳跃按钮文字 | text | JUMP |  |
| audio_text／声音设置文字 | text | AUDIO |  |
| close_text／关闭按钮文字 | text | CLOSE |  |
| score_text／分数标签 | text | SCORE |  |
| best_text／最高分标签 | text | BEST |  |
| subtitle／标题说明 | text | Jump. Avoid. Try again. |  |

### 音频总线混音（mixer）

音频总线混音：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：无。

此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| Master／总音量／dB | number | 0.0 | -60～6 |
| BGM／背景音乐／dB | number | -12.0 | -60～6 |
| SFX／游戏音效／dB | number | -4.0 | -60～6 |
| UI／界面声音／dB | number | -8.0 | -60～6 |

### 画面比例（screen）

画面比例：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：无。

此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| width／基础画面宽度 | integer | 960 | 480～3840 |
| height／基础画面高度 | integer | 540 | 240～2160 |
| aspect／画面适配 | choice | keep | expand：扩展可见区域；keep：保持比例／黑边 |
| pixel／像素最近邻显示 | bool | 开 |  |

### 播放声音（audio）

播放声音：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 播放（执行）；1 停止（执行）；2 暂停（执行）；3 继续（执行）

输出：0 播放结束（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| path／音频文件 | asset |  | audio |
| channel／输出总线 | choice | SFX | BGM：背景音乐；SFX：游戏音效；UI：界面声音 |
| loop／循环播放 | bool | 关 |  |
| volume／独立音量／dB | number | 0.0 | -60～6 |
| voices／同时播放数量 | integer | 2 | 1～8 |
| demo／空文件时使用演示音色 | choice | jump | click：演示按钮；death：演示死亡；jump：演示跳跃；music：演示配乐；none：静音；step：演示脚步 |

### 计时器（timer）

计时器：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 启动（执行）；1 停止（执行）；2 重置（执行）

输出：0 到时（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| seconds／间隔／秒 | number | 1.0 | 0.01～120 |
| repeat／重复 | bool | 开 |  |

### 条件分支（branch）

条件分支：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 判断（执行）；1 布尔条件（布尔）

输出：0 成立（执行）；1 不成立（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| condition／判断条件 | choice | running | dead：游戏已结束；grounded：角色已落地；paused：游戏已暂停；running：游戏进行中；score：达到分数 |
| threshold／分数阈值 | number | 100.0 | 0～100000 |

### 顺序执行（sequence）

兼容旧图：立即依次触发两个输出，不等待下游异步任务。需要等待请使用串行／并行任务。

输入：0 执行（执行）

输出：0 先执行1（执行）；1 再执行2（执行）

无参数，按执行连线编排。

### 延迟（delay）

延迟：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）

输出：0 等待后（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| seconds／等待／秒 | number | 0.5 | 0.01～120 |

### 布尔变量（boolean）

布尔变量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 布尔值（布尔）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／变量名称 | text | can_act |  |
| value／初始值 | bool | 开 |  |

### 自定义模块（custom）

自定义模块：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）

输出：0 完成（执行）；1 备用（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| script／模块脚本 | asset |  | script |

### 界面按钮（button）

原生Button／TextureButton的四状态、声音和五事件。动效复用通用动画；Container中通过可恢复包装保持布局。

输入：0 启用（执行）；1 禁用（执行）；2 显示（执行）；3 隐藏（执行）；4 点击（执行）

输出：0 点击时（执行）；1 按下时（执行）；2 释放时（执行）；3 鼠标进入（执行）；4 鼠标离开（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／绑定现有按钮（空则创建） | text |  |  |
| widget／新建控件类型 | choice | button | button：Button文字按钮；texture：TextureButton图片按钮 |
| text／文字 | text | BUTTON |  |
| disabled／初始禁用 | bool | 关 |  |
| x／新建位置X | number | 60.0 | -10000～10000 |
| y／新建位置Y | number | 60.0 | -10000～10000 |
| width／新建宽度 | number | 200.0 | 1～4096 |
| height／新建高度 | number | 64.0 | 1～4096 |
| normal_texture／普通贴图 | asset |  | image |
| hover_texture／悬停贴图 | asset |  | image |
| pressed_texture／按下贴图 | asset |  | image |
| disabled_texture／禁用贴图 | asset |  | image |
| hover_sound／悬停音效 | asset |  | audio |
| click_sound／点击音效 | asset |  | audio |
| volume／独立音量／dB | number | -8.0 | -60～6 |
| bus／输出总线 | choice | UI | BGM：背景音乐；Master：总线；SFX：游戏音效；UI：界面声音 |
| effects_enabled／启用按钮动效 | bool | 关 |  |
| hover_scale／悬停缩放倍率 | number | 1.1 | 0.01～10 |
| pressed_scale／按下缩放倍率 | number | 0.95 | 0.01～10 |
| effect_seconds／反馈过渡秒数 | number | 0.12 | 0.001～5 |
| click_animation／点击播放Animation／Library | asset |  | animation_source |

### 黑板变量（blackboard）

声明场景／子图局部变量或框架全局变量。全局变量跨场景保留；重置开关明确控制是否重新初始化。

输入：无。

输出：0 当前值（数字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／变量名 | text | value |  |
| scope／变量范围 | choice | game | game：本游戏实例；project：跨场景全局 |
| value_type／类型 | choice | number | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| number／初始数字 | number | 0.0 | -1000000～1000000 |
| text／初始文字 | text |  |  |
| bool／初始布尔值 | bool | 关 |  |
| json／复杂类型初始值JSON | json | null |  |
| reset／本局变量重开恢复 | bool | 开 |  |
| reset_global／全局变量也随单局重置 | bool | 关 |  |

### 写入变量（set_variable）

写入变量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 写入（执行）；1 值（数字）

输出：0 完成（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／变量名 | text | value |  |
| scope／变量范围 | choice | game | game：本游戏实例；project：跨场景全局 |
| value_type／类型 | choice | number | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| number／默认数字 | number | 0.0 | -1000000～1000000 |
| text／默认文字 | text |  |  |
| bool／默认布尔值 | bool | 关 |  |
| json／复杂类型默认值JSON | json | null |  |

### 数字常量（number）

数字常量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 数字（数字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| value／数字 | number | 1.0 | -1000000～1000000 |

### 文字常量（text）

文字常量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 文字（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| value／文字 | text | Hello |  |

### 数字运算（math）

数字运算：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 A（数字）；1 B（数字）

输出：0 结果（数字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| op／计算 | choice | add | add：加；divide：除；max：取大；min：取小；multiply：乘；subtract：减 |
| a／未接线时A | number | 0.0 | -1000000～1000000 |
| b／未接线时B | number | 1.0 | -1000000～1000000 |

### 数字比较（compare）

数字比较：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 A（数字）；1 B（数字）

输出：0 结果（布尔）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| op／比较 | choice | greater | equal：近似相等；greater：大于；greater_equal：大于等于；less：小于；less_equal：小于等于 |
| a／未接线时A | number | 0.0 | -1000000～1000000 |
| b／未接线时B | number | 1.0 | -1000000～1000000 |

### 布尔运算（logic）

布尔运算：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 A（布尔）；1 B（布尔）

输出：0 结果（布尔）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| op／逻辑 | choice | and | and：同时成立；not：A不成立；or：至少一个成立 |
| a／未接线时A | bool | 关 |  |
| b／未接线时B | bool | 关 |  |

### 读取游戏数据（game_value）

读取游戏数据：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 值（数字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| field／数据 | choice | score | best：最高分；current_speed：滚动速度；delta：帧间隔；elapsed：本局秒数；score：分数 |

### 只执行一次（do_once）

只执行一次：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）；1 重置（执行）

输出：0 通过（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| closed／初始关闭 | bool | 关 |  |

### 执行闸门（gate）

执行闸门：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）；1 打开（执行）；2 关闭（执行）；3 切换（执行）

输出：0 通过（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| open／初始打开 | bool | 开 |  |

### 交替执行（flip_flop）

交替执行：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）；1 重置（执行）

输出：0 A（执行）；1 B（执行）；2 本次为A（布尔）

无参数，按执行连线编排。

### 冷却限制（cooldown）

冷却限制：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）；1 重置（执行）

输出：0 通过（执行）；1 冷却中（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| seconds／冷却秒数 | number | 0.5 | 0.01～120 |

### 状态机（fsm）

状态机：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 重置（执行）

输出：0 进入状态（执行）；1 当前状态（文字）；2 离开状态（执行）；3 上一状态（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／状态机名 | text | player_state |  |
| states／状态（逗号分隔） | text | idle,move,attack,dead |  |
| initial／初始状态 | text | idle |  |
| transitions／允许转换（空表示任意已知状态） | text |  |  |

### 切换状态（set_state）

切换状态：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）

输出：0 成功（执行）；1 拒绝（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／状态机名 | text | player_state |  |
| state／目标状态 | text | move |  |

### 发送命名事件（event_emit）

发送命名事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 发送（执行）；1 消息（文字）

输出：0 已发送（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／事件名 | text | collected |  |
| text／消息 | text |  |  |

### 接收命名事件（event_listener）

接收命名事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 收到（执行）；1 消息（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／事件名 | text | collected |  |

### 生命值（health）

生命值：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 伤害（执行）；1 恢复（执行）；2 重置（执行）；3 数量（数字）

输出：0 变化（执行）；1 耗尽（执行）；2 当前生命（数字）；3 生命比例（数字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| max／生命上限 | number | 100.0 | 1～1000000 |
| initial／初始生命 | number | 100.0 | 0～1000000 |
| amount／默认伤害／恢复量 | number | 10.0 | 0～1000000 |
| invulnerability／受伤保护秒数 | number | 0.3 | 0～60 |
| show／在界面显示 | bool | 开 |  |
| caption／界面标题 | text | HP |  |

### 生成场景实例（spawn_scene）

生成场景实例：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 生成（执行）；1 清理本模块实例（执行）；2 X（数字）；3 Y（数字）

输出：0 成功（执行）；1 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| scene／场景文件 | asset |  | scene |
| name／实例名称 | text | Entity |  |
| x／X | number | 200.0 | -100000～100000 |
| y／Y | number | 200.0 | -100000～100000 |
| limit／最多存活实例 | integer | 16 | 1～64 |

### 场景节点操作（node_action）

场景节点操作：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）；1 X（数字）；2 Y（数字）

输出：0 成功（执行）；1 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标路径（相对游戏根节点） | text | Entity |  |
| op／操作 | choice | show | animation：播放动画；disable：禁用处理；enable：启用处理；free：删除；hide：隐藏；position：设置位置；show：显示；translate：移动距离；velocity：设置角色速度 |
| x／X | number | 0.0 | -100000～100000 |
| y／Y | number | 0.0 | -100000～100000 |
| clip／动画名 | text | idle |  |

### 场景信号事件（signal_event）

场景信号事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 触发（执行）；1 首个参数（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标路径（相对游戏根节点） | text | Entity |  |
| signal／信号名 | text | tree_exiting |  |

### 调试记录（log）

调试记录：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）；1 文字（文字）

输出：0 完成（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| text／文字 | text | Blueprint event |  |

### 可复用子图（module）

可复用子图：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）

输出：0 完成（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| path／子图文件 | asset |  | module |

### 自定义按键事件（key_event）

自定义按键事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 按下（执行）；1 释放（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| key／按键 | key | J |  |
| running_only／仅在游戏进行时触发 | bool | 开 |  |

### 文字格式化（format_text）

文字格式化：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 值（数字）

输出：0 文字（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| value_type／输入类型 | choice | number | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| template／文字（{value}为值） | text | Value: {value} |  |

### 界面提示（ui_message）

界面提示：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 显示（执行）；1 文字（文字）

输出：0 完成（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| text／显示文字 | text | Complete |  |
| seconds／显示秒数 | number | 2.0 | 0.1～60 |

### 通用动画（animation）

统一属性Tween、AnimationPlayer与SpriteFrames任务。完成、取消、失败分别连线；无限循环需关闭等待。停止恢复由恢复初始开关控制。

输入：0 播放（执行）；1 停止（执行）；2 暂停（执行）；3 恢复（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| mode／动画类型 | choice | scale | animation：Animation／AnimationPlayer；color：RGBA；frames：SpriteFrames；position：位置；scale：缩放（放大／缩小） |
| factor／目标缩放倍率 | number | 1.2 | 0.001～100 |
| x／目标X／相对位移X | number | 0.0 | -100000～100000 |
| y／目标Y／相对位移Y | number | -30.0 | -100000～100000 |
| relative／位置使用相对位移 | bool | 开 |  |
| color／目标RGBA | color | ffffff00 |  |
| use_from／使用指定起点 | bool | 关 |  |
| from_x／起点X／缩放X | number | 1.0 | -100000～100000 |
| from_y／起点Y／缩放Y | number | 1.0 | -100000～100000 |
| from_color／起点RGBA | color | ffffffff |  |
| seconds／持续秒数 | number | 0.3 | 0.001～120 |
| delay／开始延迟 | number | 0.0 | 0～120 |
| transition／Transition | choice | sine | back：Back；bounce：Bounce；cubic：Cubic；elastic：Elastic；linear：Linear；quad：Quad；sine：Sine |
| ease／Ease | choice | in_out | in：In；in_out：InOut；out：Out；out_in：OutIn |
| loops／循环次数（0无限） | integer | 1 | 0～1000 |
| reverse／反向播放 | bool | 关 |  |
| pingpong／属性动画往返 | bool | 关 |  |
| restore／结束／取消恢复初始 | bool | 关 |  |
| wait／等待结束 | bool | 开 |  |
| ui／暂停时继续（UI） | bool | 关 |  |
| policy／属性冲突 | choice | replace | reject：拒绝新动画；replace：取消旧动画并替换 |
| animation／Animation／Library资源 | asset |  | animation_source |
| player／已有Player相对子路径 | text | AnimationPlayer |  |
| frames／SpriteFrames资源 | asset |  | frames |
| clip／片段名称（空则首个） | text |  |  |
| speed／播放速度 | number | 1.0 | 0.01～100 |
| retarget／所有轨道绑定到目标本身 | bool | 关 |  |
| remap／轨道节点重映射JSON | json | {} |  |
| timeout／等待超时／秒 | number | 120.0 | 0.01～3600 |

### 串行／并行任务（task_group）

每个分支包含下游完整流程。串行等待前一分支真正结束；并行等待全部结束。旧顺序模块保持立即依次发出信号。

输入：0 执行（执行）；1 取消（执行）

输出：0 分支1（执行）；1 分支2（执行）；2 分支3（执行）；3 分支4（执行）；4 全部完成（执行）；5 取消（执行）；6 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| mode／编排 | choice | serial | parallel：并行：等待全部分支；serial：串行：等待前一分支 |
| branches／使用分支数 | integer | 2 | 1～4 |
| wait／等待全部结束 | bool | 开 |  |
| ui／暂停时继续（UI） | bool | 关 |  |
| timeout／超时／秒 | number | 120.0 | 0.01～3600 |
| retrigger／重复触发 | choice | replace | ignore：忽略重复触发；replace：取消旧任务并重启 |

### 可等待延迟（wait_task）

受游戏暂停控制的可取消延迟；UI开关允许暂停时继续。

输入：0 等待（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| seconds／等待秒数 | number | 0.3 | 0～3600 |
| ui／暂停时继续（UI） | bool | 关 |  |

### 通用UI操作（ui_control）

创建或绑定原生控件，写入指定值。值类型必须与目标属性匹配；可用数据线动态输入。

输入：0 执行（执行）；1 值（文字）；2 目标（节点引用）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| create_type／目标留空时创建 | choice | none | Button：Button；CheckBox：CheckBox；Control：Control；HSlider：Slider；Label：Label；LineEdit：LineEdit；Panel：Panel；PanelContainer：PanelContainer；ProgressBar：ProgressBar；RichTextLabel：RichTextLabel；TextureButton：TextureButton；TextureRect：TextureRect；none：仅绑定已有控件 |
| name／新控件名 | text | Element |  |
| parent／父节点（可选Container） | node |  |  |
| x／新建X | number | 40.0 | -10000～10000 |
| y／新建Y | number | 40.0 | -10000～10000 |
| width／新建宽度 | number | 200.0 | 1～4096 |
| height／新建高度 | number | 48.0 | 1～4096 |
| operation／UI操作 | choice | show | alpha：透明度；color：RGBA；disabled：禁用状态；editable：可编辑状态；focus：获取焦点；hide：隐藏；position：位置；show：显示；size：尺寸；text：文字；texture：图片；value：数值 |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| json／默认值JSON（向量用数组、节点用路径） | json | null |  |

### UI事件（ui_event）

绑定原生节点信号。最多四参数时取第一参数；无参数发出所选类型默认值。目标可为场景物体或UI。

输入：无。

输出：0 触发（执行）；1 参数（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| signal／原生信号 | text | pressed |  |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| ui／游戏暂停时触发 | bool | 开 |  |

### 获取节点引用（node_ref）

获取节点引用：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 节点（节点引用）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |

### 读取属性（property_get）

读取属性：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 目标（节点引用）

输出：0 值（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| property／支持的属性 | property | position |  |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |

### 修改属性（property_set）

修改属性：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）；1 值（文字）；2 目标（节点引用）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| property／支持的属性 | property | position |  |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| json／默认值JSON（向量用数组、节点用路径） | json | null |  |

### 受支持方法（method_call）

受支持方法：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 执行（执行）；1 参数数组（Array）；2 目标（节点引用）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| method／受支持方法 | choice | show | clear：clear；grab_focus：grab_focus；hide：hide；make_current：make_current；move_and_slide：move_and_slide（角色移动并滑动）；release_focus：release_focus；reset_smoothing：reset_smoothing；select_all：select_all；set_pressed_no_signal：set_pressed_no_signal；set_value_no_signal：set_value_no_signal；show：show |
| arguments／参数JSON数组 | json | [] |  |

### 获取资源引用（resource_ref）

获取资源引用：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 资源（Resource）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| resource／资源 | asset |  | resource |

### 类型化常量（typed_value）

类型化常量：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 值（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| json／默认值JSON（向量用数组、节点用路径） | json | null |  |

### 数组／字典操作（collection）

数组／字典操作：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 集合（Dictionary）；1 值（文字）

输出：0 结果（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| operation／集合操作 | choice | get | append：追加到副本；erase：从副本删除；get：按键／下标读取；set：写入副本；size：元素数量 |
| container／集合类型 | choice | dictionary | array：Array；dictionary：Dictionary |
| key／字典键／数组下标 | text | 0 |  |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| json／默认集合JSON | json | {} |  |

### 发送参数事件（event_send）

发送带类型参数的命名事件；本游戏、指定角色或框架跨场景作用域。

输入：0 发送（执行）；1 参数（文字）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／事件名 | text | event |  |
| scope／作用域 | choice | game | game：本游戏实例；project：本游戏框架跨场景；role：指定角色 |
| target／目标节点 | node |  |  |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| json／默认值JSON（向量用数组、节点用路径） | json | null |  |

### 接收参数事件（event_receive）

订阅带参数事件；场景退出自动退订。接收类型需与发送端一致。

输入：无。

输出：0 收到（执行）；1 参数（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／事件名 | text | event |  |
| scope／作用域 | choice | game | game：本游戏实例；project：本游戏框架跨场景；role：指定角色 |
| target／目标节点 | node |  |  |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |

### 子图输入参数（module_input）

定义子图命名输入与默认值；将值连到需要的数据口。

输入：无。

输出：0 值（文字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／输入参数名 | text | value |  |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| json／默认值JSON（向量用数组、节点用路径） | json | null |  |

### 子图返回参数（module_output）

定义命名返回值并执行返回。子图到达选定执行出口后，调用节点输出返回字典。

输入：0 返回（执行）；1 值（文字）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／返回参数名 | text | result |  |
| value_type／数据类型 | choice | text | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| json／默认值JSON（向量用数组、节点用路径） | json | null |  |

### 参数化子图（subgraph）

带命名参数与返回字典的可等待子图，局部变量隔离。保存场景时编译冻结，源JSON可不随运行包。

输入：0 执行（执行）；1 参数字典（Dictionary）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）；3 返回字典（Dictionary）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| path／参数化子图文件 | asset |  | module |
| arguments／默认参数JSON字典 | json | {} |  |
| timeout／等待超时／秒 | number | 120.0 | 0.01～3600 |

### Camera2D控制（camera2d）

相机移动、跟随、缩放、旋转、震动、切换与边界。有限过渡可串并行等待；持续跟随在配置完成后输出完成。

输入：0 执行（执行）；1 取消（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| operation／相机操作 | choice | move | current：切换为当前；follow：跟随目标；limits：设置边界；move：平滑移动；offset：视角偏移；rotate：旋转；shake：震动；stop_follow：停止跟随；zoom：缩放 |
| follow／跟随目标 | node |  |  |
| x／X／缩放X／边界左 | number | 0.0 | -100000～100000 |
| y／Y／缩放Y／边界上 | number | 0.0 | -100000～100000 |
| right／边界右 | number | 10000.0 | -100000～100000 |
| bottom／边界下 | number | 10000.0 | -100000～100000 |
| angle／旋转度数 | number | 0.0 | -3600～3600 |
| strength／震动幅度 | number | 8.0 | 0～1000 |
| seconds／过渡秒数 | number | 0.4 | 0.001～120 |
| smoothing／跟随平滑速度 | number | 6.0 | 0～100 |
| ui／暂停时继续 | bool | 关 |  |

### 背景／视差（background）

原生Sprite2D／Parallax2D，多层、尺寸、平铺与自动滚动。背景动画请连通用动画模块。

输入：0 创建／更新（执行）；1 显示（执行）；2 隐藏（执行）；3 删除（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）；3 对象（节点引用）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| image／背景图片 | asset |  | image |
| name／新建名称 | text | Background |  |
| x／X | number | 0.0 | -100000～100000 |
| y／Y | number | 0.0 | -100000～100000 |
| width／显示宽度（0原尺寸） | number | 0.0 | 0～100000 |
| height／显示高度（0原尺寸） | number | 0.0 | 0～100000 |
| rotation／旋转角度 | number | 0.0 | -3600～3600 |
| alpha／透明度 | number | 1.0 | 0～1 |
| layer／显示层级 | integer | -10 | -4096～4096 |
| repeat_x／平铺宽度（0关闭） | number | 0.0 | 0～100000 |
| repeat_y／平铺高度 | number | 0.0 | 0～100000 |
| parallax／使用Parallax2D | bool | 关 |  |
| scroll_x／自动滚动X | number | 0.0 | -10000～10000 |
| scroll_y／自动滚动Y | number | 0.0 | -10000～10000 |
| ratio_x／视差倍率X | number | 0.5 | -10～10 |
| ratio_y／视差倍率Y | number | 0.5 | -10～10 |

### TileMapLayer地图（tilemap）

绑定或创建TileMapLayer。复杂地图、地形与碰撞在Godot原生编辑器配置；本模块修改格子并记录存档差量。大区域每帧批处理。

输入：0 执行（执行）；1 坐标（Vector2）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）；3 格子数据（Dictionary）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| tileset／TileSet资源 | asset |  | tileset |
| name／新建图层名 | text | Ground |  |
| operation／地图操作 | choice | bind | bind：创建／绑定；cell_to_world：格子转世界；clear：清空图层；clear_region：清除矩形；enabled：图层启停；erase：删除格子；fill：填充矩形；read：读取格子；set：放置／替换；terrain：地形自动连接；world_to_cell：世界坐标转格子 |
| x／格子／坐标X | integer | 0 | -100000～100000 |
| y／格子／坐标Y | integer | 0 | -100000～100000 |
| width／区域宽度 | integer | 1 | 1～512 |
| height／区域高度 | integer | 1 | 1～512 |
| source／瓦片源ID | integer | 0 | 0～100000 |
| atlas_x／图集X | integer | 0 | 0～100000 |
| atlas_y／图集Y | integer | 0 | 0～100000 |
| alternative／替代瓦片ID | integer | 0 | 0～100000 |
| terrain_set／地形集合ID | integer | 0 | 0～1000 |
| terrain／地形ID | integer | 0 | 0～1000 |
| layer／绘制层级 | integer | 0 | -4096～4096 |
| enabled／图层启用 | bool | 开 |  |
| collision／启用TileSet碰撞 | bool | 开 |  |
| save_key／地图存档标识 | text | ground |  |

### 场景物体（scene_object）

创建图片、SpriteFrames或PackedScene；绑定现有对象可显示、变换、播放动画。删除端口只删除此模块创建的对象。

输入：0 创建／更新（执行）；1 显示（执行）；2 隐藏（执行）；3 删除（执行）；4 播放动画（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）；3 对象（节点引用）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| kind／资源类型 | choice | image | frames：SpriteFrames；image：图片Sprite2D；scene：PackedScene |
| resource／资源 | asset |  | resource |
| name／新对象名 | text | Entity |  |
| x／X | number | 0.0 | -100000～100000 |
| y／Y | number | 0.0 | -100000～100000 |
| scale_x／缩放X | number | 1.0 | -100～100 |
| scale_y／缩放Y | number | 1.0 | -100～100 |
| rotation／旋转度数 | number | 0.0 | -3600～3600 |
| layer／显示层级 | integer | 0 | -4096～4096 |
| collision／矩形碰撞 | bool | 关 |  |
| width／碰撞宽度 | number | 32.0 | 1～4096 |
| height／碰撞高度 | number | 32.0 | 1～4096 |
| clip／动画名 | text | default |  |

### InputMap动作（input_action）

读取Godot InputMap，输出按下、释放、按住与强度。输入框聚焦时默认屏蔽游戏输入。

输入：无。

输出：0 按下（执行）；1 释放（执行）；2 按住（执行）；3 强度（数字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| action／InputMap动作 | input_action | Jump |  |
| running_only／仅游戏进行时 | bool | 开 |  |
| allow_ui_focus／输入控件聚焦时仍触发 | bool | 关 |  |

### 运行时改键（input_bind）

为动作绑定多个键或鼠标、捕获新键、处理冲突、恢复默认并写入独立设置文件。

输入：0 执行（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| action／动作名称 | input_action | Jump |  |
| operation／操作 | choice | bind | add：追加绑定；bind：替换绑定；capture：运行时捕获下一次输入；reset：恢复默认；save：保存键位 |
| bindings／绑定JSON数组 | json | [{"key":32}] |  |
| conflict／冲突策略 | choice | reject | reject：拒绝冲突；share：允许共享；steal：从其它动作移除 |

### 音频渐变／位置声音（audio_fx）

音频渐变／位置声音：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 播放（执行）；1 停止（执行）；2 暂停（执行）；3 恢复（执行）；4 淡入（执行）；5 淡出（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| path／音频资源 | asset |  | audio |
| channel／输出总线 | choice | SFX | BGM：背景音乐；Master：总线；SFX：游戏音效；UI：界面声音 |
| volume／目标音量dB | number | 0.0 | -80～6 |
| seconds／渐变秒数 | number | 0.3 | 0.001～120 |
| loop／循环 | bool | 关 |  |
| spatial／位置音效 | bool | 关 |  |
| x／位置X | number | 0.0 | -100000～100000 |
| y／位置Y | number | 0.0 | -100000～100000 |
| wait／等待播放完成 | bool | 关 |  |
| timeout／超时／秒 | number | 120.0 | 0.01～3600 |

### 游戏生命周期（game_service）

初始化、开始、暂停、继续、结束、重开、返回菜单与退出。框架暂停冻结世界，UI任务可继续。

输入：0 执行（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| operation／生命周期 | choice | start | end：结束；initialize：初始化；menu：返回主菜单；pause：暂停；quit：退出游戏；restart：重新开始；resume：恢复；start：开始 |

### 场景切换／转场（scene_service）

切换或预加载场景。叠加界面可以独立编辑，打开时可暂停当前游戏，关闭后继续原局。

输入：0 执行（执行）；1 取消（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| operation／场景操作 | choice | change | change：切换；close_overlay：关闭当前叠加界面；menu：返回主菜单；open_overlay：打开叠加界面；preload：预加载；reload：重载 |
| scene／目标场景 | asset |  | scene |
| fade／转场淡出／淡入秒数 | number | 0.3 | 0～10 |
| pause_world／界面打开时暂停游戏 | bool | 关 |  |

### 设置管理（settings_service）

分辨率、窗口模式、四路音量和输入绑定独立持久化，不随存档回退。

输入：0 执行（执行）；1 值（数字）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）；3 当前值（Dictionary）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| operation／设置操作 | choice | volume | load：恢复已存设置；reset：恢复全部默认；resolution：分辨率；save：保存设置；volume：音量；window：窗口模式 |
| channel／音量通道 | choice | Master | BGM：BGM；Master：Master；SFX：SFX；UI：UI |
| number／默认数值／音量dB | number | 0.0 | -80～6 |
| width／窗口宽 | integer | 1280 | 320～7680 |
| height／窗口高 | integer | 720 | 240～4320 |
| window／窗口模式 | choice | windowed | borderless：无边框；fullscreen：全屏；windowed：窗口 |

### 存档管理（save_service）

多槽存取；先恢复场景，再恢复注册变量、角色属性与地图差量。槽0为快速存档，设置单独保存。

输入：0 执行（执行）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）；3 槽位信息（Dictionary）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| operation／存档操作 | choice | save | autosave：自动保存；delete：删除；list：槽位列表；load：读取；quick_load：快速读取；quick_save：快速保存；save：创建／覆盖 |
| slot／槽位（0快速） | integer | 1 | 0～20 |
| variables／保存变量名（空为全部） | text |  |  |
| actor／角色节点 | node |  |  |
| state_keys／角色属性（逗号分隔） | text | position,velocity |  |

### 注册存档数据（data_register）

注册存档数据：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：0 注册／更新（执行）；1 数据（Dictionary）

输出：0 完成（执行）；1 取消（执行）；2 失败（执行）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| name／注册数据名 | text | quest |  |
| value_type／数据类型 | choice | dictionary | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |
| json／默认数据JSON | json | {} |  |

### 游戏／场景事件（game_event）

游戏／场景事件：从执行口触发，在右侧配置参数与资源；数据口按类型连接。

输入：无。

输出：0 发生（执行）；1 参数（Dictionary）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| event／生命周期事件 | choice | initialized | ended：结束；initialized：初始化完成；loaded：存档恢复完成；paused：暂停；restarted：重开；resumed：恢复；scene_entered：场景进入；scene_exiting：场景退出；settings_changed：设置改变；started：开始 |
| value_type／参数类型 | choice | dictionary | array：数组；bool：布尔；color：颜色RGBA；dictionary：字典；node：节点引用；number：数字；resource：资源引用；text：文字；vector2：Vector2；vector3：Vector3（数据） |

### 帧更新事件（frame_event）

每个普通帧或物理帧触发一次，输出本次更新经过的秒数。

输入：无。

输出：0 更新（执行）；1 帧间隔（数字）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| clock／更新时机 | choice | physics | physics：物理帧；render：普通帧 |

### 2D接触状态（body_contact）

读取 CharacterBody2D 最近一次移动后的地面、墙壁或天花板接触状态。

输入：0 物体（节点引用）

输出：0 是否接触（布尔）

| 字段／参数 | 类型 | 默认 | 范围／选项 |
| --- | --- | --- | --- |
| target／目标节点 | node |  |  |
| surface／接触方向 | choice | floor | ceiling：天花板；floor：地面；wall：墙壁 |

## 角色模块（13类）

角色工作台负责单个角色，异步服务、地图、菜单、相机在游戏工作台编排。

| 类型 | 名称 | 端口 | 参数 |
| --- | --- | --- | --- |
| key | 按键 | 0按住、1按下 | code或input_action；可选InputMap默认动作或自定义名称 |
| event | 角色事件 | 0发生 | ready／hurt／death／land／animation_finished |
| action | 封装动作 | 0执行→0动画 | 19项动作；同类动作只声明一次 |
| animation | SpriteFrames | 0执行→0动画时刻 | clip动画名，实际素材必须存在 |
| sound | 音效 | 0播放 | path／trigger=start,frame,repeat／frame／interval／volume |
| branch | 条件 | 0执行、1布尔→0真、1假 | condition／invert；已落地、空中、移动、奔跑、始终 |
| sequence | 顺序 | 0执行→0、1 | 立即发出两个执行，不等待 |
| delay | 延迟 | 0执行→0完成 | seconds：0.01–60秒 |
| boolean | 布尔变量 | 0布尔数据 | name／value |
| custom | 自定义脚本 | 0执行→0、1 | RefCounted.execute(context)，同步接口 |
| receive_event | 接收参数事件 | 0事件、1类型化参数 | name／scope=game,project,role／value_type |
| send_event | 发送参数事件 | 0执行、1类型化数据→0完成 | name／scope／value_type／json |
| typed_value | 类型化常量 | 0类型化数据 | value_type／json |

复杂类型支持bool／number／text／Vector2／Vector3数据／Color／Node／Resource／Array／Dictionary。JSON向量写数组、颜色写HTML、资源写res://路径、节点写角色下的相对路径。

角色默认运动参数：速度180、奔跑倍率1.8、重力980、起跳速度-380。角色动作包括移动、待机、行走、奔跑、跳跃、攻击、受击、死亡、冲刺、翻滚、防御、施法、交互、攀爬、下落、落地。特殊技能仍需玩法模块或自定义代码；动作槽不自动提供命中判定、背包或AI。

## 模板与边界

新建游戏框架提供空白2D、基础2D、平台跳跃、跑酷；生成六类可编辑原生场景。菜单、保存与设置接线和动画均有效。只创建新目录，只有用户勾选才修改启动场景。

旧自含游戏API低于6时只读绑定，创建新名称场景升级。原Sequence保持立即双输出，等待请用task_group。旧v1子图仍可加载，参数子图保存为version2。

3D／2.5D暂缓；不包含完整行为树、多人联网、整套装备／任务／对话编辑器或自动关卡美术识别。使用Godot原生TileSet／TileMapLayer编辑器设计地图，蓝图负责动态逻辑。蓝图执行不启动AI推理。
