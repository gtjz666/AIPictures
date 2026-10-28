# 架构与阶段边界

项目独立于 AIGAMING、Godot 和 ComfyUI 源码。界面只依赖轻量客户端环境，不在其中安装 Torch、训练框架或 ComfyUI 自定义节点。

## 当前完整骨骼动画模块

标准界面只提供完整姿态序列条件；历史自由 I2V / 网格后端保留作旧缓存及诊断。动画类型和风格 LoRA 都由用户明确选择，动作宏自动写入实际条件，不调用 LLM 分类。

- `animation_actions.py`：五种动作名称和中文动作宏；`motion_clip.py`：角色相对周期、腿部 IK、跑步腾空、跳跃根位移、关键帧与插值、BODY_18 和独立跟/趾控制。模型只消费标准身体点，辅助足部控制转换为脚踝端点。
- `motion_reference.py`：本次参考的 DWPose 适配，或明确标注的双足轮廓估计；不套用另一角色坐标。输入 SHA-256 和布局信息随结果保存。
- `motion_editor.py`：Qt 拖动关节、基准/逐帧编辑、骨骼预览与保存；数据按角色校验值/动作存储，入队后深拷贝快照。修改关键帧后重新生成整个连续片段。
- `pose_animation.py`：原生 WanAnimateToVideo Move 条件图，参考图 + CLIP Vision + 平衡 ImageBatch 拼接全部姿态，TrimVideoLatent 移除参考潜帧；原生 VAE 解码。480×640、17/33 输入帧，对应 8/16 导出帧，等待上限两小时。整周期均匀取样，不做逐帧地面对齐，保留跳跃位移。
- `foot_quality.py`：有原图约束的浅色鞋局部蓝色漏色修正，只改变有限 RGB 区域，Alpha 不动，保留原图与逐帧记录；不负责拓扑修复或普遍质量评分。
- `task_display.py`：左侧当前任务名称、状态、百分比和细进度条；内部编号仅用于缓存、日志和服务端跟踪。
- `tools/prepare_pose_models.py`：固定发布版本、字节数及 SHA-256，安装 Animate FP8 和独立诊断加速 LoRA；复用既有编码器/VAE/视觉编码器，不向 UI 环境加入推理框架。

`data/animations/<任务>/motion.json` 保存 schema_version、角色校验、动作、画布、帧率、完整关键帧、基准、edited；`poses/` 保存真正上传的每帧条件。`sequence.json` schema 4 记录方法、动作、原生帧数、完整周期取样索引、状态及导出。`video/` 保存完整 API、原始 RGB、latent 和服务端任务号；`frame_XXX/` 保存输出姿态、足部检查及修正前图。向左结果统一镜像回原方向。历史兼容仍使用 kind=walk，实际动作由 action 字段区分。

## 图像、共享模块与历史后端

- `aipictures/app.py`：Qt 窗口、后台 QThread、串行本地队列和事件消费。网络和推理等待不阻塞主线程。
- `aipictures/engine.py`：本地 ComfyUI REST / WebSocket 适配器。模型发现、执行、进度、按任务取消、历史和文件下载。HTTP 超时 20 秒，单任务等待上限 30 分钟。
- `aipictures/engine_service.py`：复用已有 Windows 启动脚本，后台启动本机 8188 服务并等待就绪；启动输出写文件，不使用可能被后台子进程继承而无限等待 EOF 的 PIPE。共享空闲推理缓存释放供单图和动画在 CPU 分割前调用，有其他引擎任务则跳过。连接不可用统一为可操作的 EngineUnavailable；窗口禁用生成、暂停未开始队列，重连后继续。已提交任务不自动重跑；单独 WebSocket 断线降级为相同 prompt_id 的 HTTP 记录查询。
- `aipictures/reference_fidelity.py`：显式保真策略与低重绘上限。参考图外观优先于外观提示词；保真单图确保有源图潜空间，IP-Adapter 身份条件不能代替图生图潜空间。暂停应用本软件风格 LoRA 与超分，作者预设自带风格 / 姿态约束时明确提示选择其他策略，原文件不变。连续动画保留图像条件和朝向，补充纹样、配饰等约束，不宣称精确像素一致。
- `aipictures/ui_hints.py`：静态悬浮说明和下拉选项区别，不运行模型分析、不自动改变用户选择。
- `aipictures/workflow.py`：可序列化 ImageRequest 和 SDXL 工作流构建，LoRA 的 model/clip 与 VAE 独立连接。
- `aipictures/lora_catalog.py` / `resources/lora_catalog.json`：静态人工登记的风格标签、SDXL 兼容性、强度、触发词与固定版本下载信息。类型筛选只改列表，具体 LoRA 由用户手选，提示词不参与选择。独立的标记层接入 checkpoint 的 model / clip 输出，覆盖 IP-Adapter 上游；重复绑定替换本软件的层，保留作者原有层及 VAE。
- `aipictures/image_quality.py`：轮廓 Alpha 的轻量平滑，以及显式可选的 Real-ESRGAN 工作流。标准模式不加载超分模型。连续动画先选帧、释放 Wan 缓存，再提交独立高清任务；按 SaveImage 节点 ID 重排返回帧，随后统一抠图和稳定。缓存清理包含高清中间文件，原始连续帧保留。
- `tools/prepare_style_models.py`：固定 LoRA 提交与 SHA-256 下载校验；官方 Real-ESRGAN 发布文件按大小检查并记录 SHA-256。模型装在 ComfyUI 模型目录，不进入 Git。无需修改原 ComfyUI 工作流或安装额外 Python 依赖。
- `aipictures/storage.py`：项目数据根、原子 JSON 写入、任务目录。输出与源码分离。
- `aipictures/workflow_editor.py`：Qt WebEngine 内嵌本地 ComfyUI 前端，独立 profile/cache；通过异步 JavaScript 桥接读写画布副本、导出 UI/API、向 app 发出运行请求。前端通过本机公开的 comfyAPI/app 接口转换图，不向 ComfyUI 安装扩展或修改资源。桥接接口随前端版本可能变化。
- `aipictures/workflow_library.py`：本地目录索引、导入路径解析、已安装节点/模型/输入图和连线的兼容检查。`tools/migrate_local_workflows.py` 负责非破坏性复制和来源校验，不把迁移数据放入源码目录。
- `aipictures/prompt_binding.py`：对话请求与 API 图之间的独立绑定层。根据 KSampler 正/负条件连线定位文本输入，识别 IP-Adapter 角色参考输入及 VAEEncode 图生图参考；与 ControlNet 姿态图分开处理。基础空画布图可注入图生图路径。每次绑定都深拷贝模板；多组提示词或参考输入歧义时拒绝自动绑定。
- `tests/`：结构测试与真实桌面到 ComfyUI 验收脚本。
- `aipictures/studio_layout.py`：两栏布局，按钮侧栏与并排提示词；`panels.py` 管理非模态设置小窗口、缓存/已保存文件和骨骼校对窗口，布局与执行逻辑分离。
- `aipictures/theme.py`：统一浅色 Qt 调色板和样式，预览棋盘格仅用于渲染，不改变透明输出。
- `aipictures/result_cache.py`：任务缓存目录枚举与删除、导出路径校验和已保存文件索引。清理前验证解析后的绝对目标为 jobs/animations 的直接任务子目录，拒绝根目录、外部路径及目录链接；从界面传入当前/排队目录保护列表，递归清理在工作线程执行。用户主动保存的位置必须在缓存目录之外，索引保存在 data/saved-files.json，缓存清理不修改该索引或外部文件。
- `aipictures/character_profile.py`：版本化角色提示词、BODY_18 骨架、姿态草案和参考重绘/骨骼控制两条独立图构建器；图片、姿态和完整工作流实例在 data/characters 中保存。
- `aipictures/action_intent.py`：有限中文动作词表、否定处理与英文条件映射；保存识别/未识别内容，不调用云端语言服务。单张图按动作选择姿态图，行走由生成类型显式选择。
- `aipictures/prompt_text.py`：单图 SDXL / 旧版骨骼的有限中文外观与反向词映射，未映射负向词保留原文并报告；Wan 使用完整中文原文。动画动作由选择框决定，外观补充会移除冲突的站立等姿势指令。
- `aipictures/temporal_animation.py`：历史自由 I2V 后端，Wan2.2 14B 的高 / 低噪声专家连续采样、非人体参考准备、文字模式角色图生成、透明背景处理、整帧稳定和循环区间选择。两专家共享视频潜空间，无人体骨骼检测或肢体分层。使用原生连续 VAE 解码，保存原始采样 latent，便于复查解码而不重新推理。576×768 原始连续帧保留在 video/，同一尺度的输出为 768×1024；单次连续推理等待上限 2 小时。确认后端队列空闲后释放推理缓存，为 CPU 透明处理腾出内存，有其他任务时跳过。生成、保存和取消共用现有串行队列，界面不加载 Torch。
- `aipictures/background.py`：本地 CPU IS-Net / BiRefNet 会话、Alpha 分割和原图备份。配置 data/background-settings.json 选择权重及根目录，模型文件必须已安装；生成时不隐式联网下载。保留导入 PNG 的有效 Alpha，只计算生成 RGB 的遮罩。默认 CPU 线程数为 6，任务结束及下一次大模型推理前销毁会话，释放内存。旧自由 I2V 按缩略图选帧，新 Animate 按完整周期取样；均仅分割最终 8 / 16 帧，每 4 帧重建会话，避免长批次 CPU 内存池累积。
- `tools/rebuild_animation_mattes.py`：复用已完成的连续动画原始 RGB，调用与生产相同的 finish_sequence 后处理；先在任务内临时目录完成全部输出，再备份旧文件并替换。不会提交新的 ComfyUI 推理任务，不处理其他目录或旧版骨骼缓存。
- `tools/prepare_wan_models.py`：只在显式 --download 时下载指定版本权重；固定仓库提交、按 Range 断点续传、SHA-256 校验后才安装。已有不同内容模型不覆盖；局部文件保留为 .part，模型目录不纳入 Git。
- `aipictures/reference_analysis.py`：保留输入 Alpha、主体归一化、DWPose 身体/手部坐标提取、侧视骨骼标定和按图片 SHA-256 的识别缓存。姿态检测使用已有 ComfyUI 节点的 openpose_json 返回，不向 UI 环境安装 Torch。遮挡侧由可见侧估计，元数据明确记录。
- `aipictures/skin_warp.py`：根据参考颜色及关节分层、手部轮廓约束、连续三角网格和预乘 Alpha 插值后还原 straight RGB；衣物补色取自同图，局部修复限制颜色变化，输出每帧质量记录。
- `aipictures/walk_cycle.py`：按测量骨长的周期骨骼、腿部 IK、逐帧 ComfyUI 工作流及透明 PNG / Sprite Sheet / GIF 导出。GIF 共享前景调色板且保留独立透明索引；与单图共用 GPU 队列，文件和执行生命周期独立。
- `aipictures/animation_player.py` / `sequence_preview.py`：本地帧播放、定位、完整帧浏览、精灵图预览与 ZIP 导出；QTimer 不等待推理线程。棋盘格由 `transparent_preview.py` 绘制，不修改输出。
- `aipictures/background.py`：CPU ONNX IS-Net 主体分割；只求遮罩并直接应用到原始 RGB，避免 cutout 预乘后再次合成导致褪色，透明输入保留既有 Alpha。后台线程保留原图后生成 RGBA，独立于 ComfyUI 的 Torch 环境；模型由 `tools/prepare_background.py` 预安装。

历史网格行走任务目录为 `data/animations/<时间_UUID>/`，`job.json` 的 kind=walk，sequence.json 包含版本、FPS、画幅、地面线、固定种子、参考图校验、意图、逐帧 phase/stage/工作流/任务 ID、导出信息与状态。旧版每帧输入、遮罩、API 图和原始 AI 输出写入同名子目录，透明最终帧写入任务根。只有全部帧和导出成功才标记 completed。取消/失败保留部分数据，不重提已完成的 ComfyUI 任务。旧版左右方向通过最终统一镜像实现，骨骼记录仍是面朝右的生成条件，manifest 显式记录 mirrored。新 Animate 数据见本页前段。

任务目录 `data/jobs/<时间_UUID>/` 包含 `job.json`、`workflow.json`、`result.json`、`image_000.png`。任务记录版本为 1，kind 当前为 image，状态包括 created、queued、running、completed、failed、cancelled。随机种子在提交前固化，完整工作流和 ComfyUI history 用于复现。程序重启会重新扫描图片记录；不会自动重提中断任务，以免重复生成。崩溃时 queued/running 记录可能陈旧，可用 prompt_id 在 ComfyUI 查询。

对话入口将 UI 参数写入独立 API 任务快照，不修改模板源文件；高级编辑器直接运行仍保留画布原始参数。服务端执行最终节点与模型校验。第一阶段只内置 SDXL checkpoint 管线；FLUX 的拆分 UNet/CLIP/VAE 加载方式需专门适配，不能仅替换 checkpoint 文件名。已有有效 FLUX API 工作流可在高级编辑器直接运行，但对话自动绑定及本地权重尚未验证。

对话任务 `params.mode=chat`，保存 user_prompt、实际 positive/negative、bindings、template、reference 和 uploaded_reference。参考图先复制到 data/references，再在后台线程上传；上传与入队之间持有固定图快照，后续修改输入不改变已提交任务。上传阶段可取消，已完成的本地输入上传不自动删除。对话消息只反映任务状态，没有 LLM 层或隐式多轮上下文。

从编辑器运行时 `params.mode=workflow_editor`，同目录附带 `editor_workflow.json`（UI 工作流，保留布局）。图像页和工作流编辑器共用 `queue_graph` 执行入口；编辑时及入队时均生成独立数据快照，后续编辑不改变已经提交的任务。编辑器内部 ComfyUI 自带运行按钮属于另一个客户端，其任务不由本软件队列管理。

取消仅删除自己的 prompt_id 并使用本机已支持的 targeted interrupt，不全局清空其他客户端队列。释放显存前检查服务端是否空闲。

角色基准将固定 positive/pose_positive 与本次动作输入组合，保存 character_id、rig_id、pose、character_route。v3 配套文件独立于旧骨架；修改遮挡关节应记录版本。参考重绘使用 IPAdapterAdvanced 和 VAEEncodeTiled/VAEDecodeTiled；骨骼路线使用独立条件图，不把姿态图接到角色参考输入。客户端不因短暂 GET /history 超时重复 POST /prompt，而是继续跟踪原 prompt_id 至任务上限或取消；生成中暂停服务端显存查询。

## 后续扩展接口

第二阶段：独立训练进程 / 环境适配器，输入 DatasetManifest（版本、图片路径、标注、权利来源、预处理记录）和 TrainingRequest（框架、基础模型、参数、输出目录）；事件统一转换为任务 kind=training 的 progress/result/error。训练产物 ModelVersion 保存父模型、数据集版本、参数和校验值，注册到可配置 LoRA 目录。不得直接向界面环境安装训练依赖。

第三阶段后续：已有完整动作骨骼编辑；进一步独立的 PoseDocument 保存版本、画布尺寸、朝向、关节 ID/坐标/父子关系；AnimationDocument 保存 fps、帧号、姿态关键帧和角色参考素材 ID。姿态渲染器输出条件 PNG，由模型适配器绑定到对应输入，当前连续动画使用 Wan Animate，历史管线使用 ControlNet / IP-Adapter。时间轴独立消费任务结果。骨架迁移需显式版本转换；AIGAMING v1/v2 只作导入参考，不混用。

第四阶段：VideoRequest 与视频工作流适配器独立于游戏帧任务；共享 AssetManifest（文件、媒体类型、来源任务、校验值）。Wan 等先验证显存预算、许可证与节点支持，再添加模型配置。

尚未实现：训练、数据集编辑、通用多轨动画时间轴、独立通用视频 / MP4 编辑导出、局部重绘、LLM 多轮对话理解、断线自动恢复、实时中间图预览。Wan 视频推理当前专用于角色动作帧生成，未提供第四阶段的通用视频页面。当前显示的是采样进度及最终图片 / 动画。

游戏素材生产的后续范围、三类素材请求及导出顺序见 [路线](GAME_ART_ROADMAP.md)。
