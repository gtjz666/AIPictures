# 架构与阶段边界

项目独立于 AIGAMING、Godot 和 ComfyUI 源码。界面只依赖轻量客户端环境，不在其中安装 Torch、训练框架或 ComfyUI 自定义节点。

## 第一阶段模块

- `aipictures/app.py`：Qt 窗口、后台 QThread、串行本地队列和事件消费。网络和推理等待不阻塞主线程。
- `aipictures/engine.py`：本地 ComfyUI REST / WebSocket 适配器。模型发现、执行、进度、按任务取消、历史和文件下载。HTTP 超时 20 秒，单任务等待上限 30 分钟。
- `aipictures/workflow.py`：可序列化 ImageRequest 和 SDXL 工作流构建，LoRA 的 model/clip 与 VAE 独立连接。
- `aipictures/storage.py`：项目数据根、原子 JSON 写入、任务目录。输出与源码分离。
- `aipictures/workflow_editor.py`：Qt WebEngine 内嵌本地 ComfyUI 前端，独立 profile/cache；通过异步 JavaScript 桥接读写画布副本、导出 UI/API、向 app 发出运行请求。前端通过本机公开的 comfyAPI/app 接口转换图，不向 ComfyUI 安装扩展或修改资源。桥接接口随前端版本可能变化。
- `aipictures/workflow_library.py`：本地目录索引、导入路径解析、已安装节点/模型/输入图和连线的兼容检查。`tools/migrate_local_workflows.py` 负责非破坏性复制和来源校验，不把迁移数据放入源码目录。
- `aipictures/prompt_binding.py`：对话请求与 API 图之间的独立绑定层。根据 KSampler 正/负条件连线定位文本输入，识别 IP-Adapter 角色参考输入及 VAEEncode 图生图参考；与 ControlNet 姿态图分开处理。基础空画布图可注入图生图路径。每次绑定都深拷贝模板；多组提示词或参考输入歧义时拒绝自动绑定。
- `tests/`：结构测试与真实桌面到 ComfyUI 验收脚本。
- `aipictures/studio_layout.py`：两栏布局；`panels.py` 管理折叠设置、素材/历史对话框和骨骼校对窗口，布局与执行逻辑分离。
- `aipictures/character_profile.py`：版本化角色提示词、BODY_18 骨架、姿态草案和参考重绘/骨骼控制两条独立图构建器；图片、姿态和完整工作流实例在 data/characters 中保存。

任务目录 `data/jobs/<时间_UUID>/` 包含 `job.json`、`workflow.json`、`result.json`、`image_000.png`。任务记录版本为 1，kind 当前为 image，状态包括 created、queued、running、completed、failed、cancelled。随机种子在提交前固化，完整工作流和 ComfyUI history 用于复现。程序重启会重新扫描图片记录；不会自动重提中断任务，以免重复生成。崩溃时 queued/running 记录可能陈旧，可用 prompt_id 在 ComfyUI 查询。

对话入口将 UI 参数写入独立 API 任务快照，不修改模板源文件；高级编辑器直接运行仍保留画布原始参数。服务端执行最终节点与模型校验。第一阶段只内置 SDXL checkpoint 管线；FLUX 的拆分 UNet/CLIP/VAE 加载方式需专门适配，不能仅替换 checkpoint 文件名。已有有效 FLUX API 工作流可在高级编辑器直接运行，但对话自动绑定及本地权重尚未验证。

对话任务 `params.mode=chat`，保存 user_prompt、实际 positive/negative、bindings、template、reference 和 uploaded_reference。参考图先复制到 data/references，再在后台线程上传；上传与入队之间持有固定图快照，后续修改输入不改变已提交任务。上传阶段可取消，已完成的本地输入上传不自动删除。对话消息只反映任务状态，没有 LLM 层或隐式多轮上下文。

从编辑器运行时 `params.mode=workflow_editor`，同目录附带 `editor_workflow.json`（UI 工作流，保留布局）。图像页和工作流编辑器共用 `queue_graph` 执行入口；编辑时及入队时均生成独立数据快照，后续编辑不改变已经提交的任务。编辑器内部 ComfyUI 自带运行按钮属于另一个客户端，其任务不由本软件队列管理。

取消仅删除自己的 prompt_id 并使用本机已支持的 targeted interrupt，不全局清空其他客户端队列。释放显存前检查服务端是否空闲。

角色基准将固定 positive/pose_positive 与本次动作输入组合，保存 character_id、rig_id、pose、character_route。v3 配套文件独立于旧骨架；修改遮挡关节应记录版本。参考重绘使用 IPAdapterAdvanced 和 VAEEncodeTiled/VAEDecodeTiled；骨骼路线使用独立条件图，不把姿态图接到角色参考输入。客户端不因短暂 GET /history 超时重复 POST /prompt，而是继续跟踪原 prompt_id 至任务上限或取消；生成中暂停服务端显存查询。

## 后续扩展接口

第二阶段：独立训练进程 / 环境适配器，输入 DatasetManifest（版本、图片路径、标注、权利来源、预处理记录）和 TrainingRequest（框架、基础模型、参数、输出目录）；事件统一转换为任务 kind=training 的 progress/result/error。训练产物 ModelVersion 保存父模型、数据集版本、参数和校验值，注册到可配置 LoRA 目录。不得直接向界面环境安装训练依赖。

第三阶段：PoseDocument 保存版本、画布尺寸、朝向、关节 ID/坐标/父子关系；AnimationDocument 保存 fps、帧号、姿态关键帧和角色参考素材 ID。姿态渲染器输出条件 PNG，工作流适配器将其送到已验证 ControlNet / IP-Adapter 管线。时间轴独立消费任务结果。骨架迁移需显式版本转换；AIGAMING v1/v2 只作导入参考，不混用。

第四阶段：VideoRequest 与视频工作流适配器独立于游戏帧任务；共享 AssetManifest（文件、媒体类型、来源任务、校验值）。Wan 等先验证显存预算、许可证与节点支持，再添加模型配置。

尚未实现：训练、数据集编辑、姿态编辑、动画时间轴、视频生成、局部重绘、LLM 多轮对话理解、断线自动恢复、实时中间图预览。当前显示的是采样进度及最终图片。
