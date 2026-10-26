# 架构与阶段边界

项目独立于 AIGAMING、Godot 和 ComfyUI 源码。界面只依赖轻量客户端环境，不在其中安装 Torch、训练框架或 ComfyUI 自定义节点。

## 第一阶段模块

- `aipictures/app.py`：Qt 窗口、后台 QThread、串行本地队列和事件消费。网络和推理等待不阻塞主线程。
- `aipictures/engine.py`：本地 ComfyUI REST / WebSocket 适配器。模型发现、执行、进度、按任务取消、历史和文件下载。HTTP 超时 20 秒，单任务等待上限 30 分钟。
- `aipictures/workflow.py`：可序列化 ImageRequest 和 SDXL 工作流构建，LoRA 的 model/clip 与 VAE 独立连接。
- `aipictures/storage.py`：项目数据根、原子 JSON 写入、任务目录。输出与源码分离。
- `tests/`：结构测试与真实桌面到 ComfyUI 验收脚本。

任务目录 `data/jobs/<时间_UUID>/` 包含 `job.json`、`workflow.json`、`result.json`、`image_000.png`。任务记录版本为 1，kind 当前为 image，状态包括 created、queued、running、completed、failed、cancelled。随机种子在提交前固化，完整工作流和 ComfyUI history 用于复现。程序重启会重新扫描图片记录；不会自动重提中断任务，以免重复生成。崩溃时 queued/running 记录可能陈旧，可用 prompt_id 在 ComfyUI 查询。

自定义 API JSON 直接作为独立任务快照提交，不修改源文件；内置参数不覆盖自定义图。服务端执行节点与模型校验。第一阶段只内置 SDXL checkpoint 管线；FLUX 的拆分 UNet/CLIP/VAE 加载方式需专门适配，不能仅替换 checkpoint 文件名。已有有效 FLUX API 工作流可直接导入，但本机尚无 FLUX 权重，因此未验证。

取消仅删除自己的 prompt_id 并使用本机已支持的 targeted interrupt，不全局清空其他客户端队列。释放显存前检查服务端是否空闲。

## 后续扩展接口

第二阶段：独立训练进程 / 环境适配器，输入 DatasetManifest（版本、图片路径、标注、权利来源、预处理记录）和 TrainingRequest（框架、基础模型、参数、输出目录）；事件统一转换为任务 kind=training 的 progress/result/error。训练产物 ModelVersion 保存父模型、数据集版本、参数和校验值，注册到可配置 LoRA 目录。不得直接向界面环境安装训练依赖。

第三阶段：PoseDocument 保存版本、画布尺寸、朝向、关节 ID/坐标/父子关系；AnimationDocument 保存 fps、帧号、姿态关键帧和角色参考素材 ID。姿态渲染器输出条件 PNG，工作流适配器将其送到已验证 ControlNet / IP-Adapter 管线。时间轴独立消费任务结果。骨架迁移需显式版本转换；AIGAMING v1/v2 只作导入参考，不混用。

第四阶段：VideoRequest 与视频工作流适配器独立于游戏帧任务；共享 AssetManifest（文件、媒体类型、来源任务、校验值）。Wan 等先验证显存预算、许可证与节点支持，再添加模型配置。

尚未实现：训练、数据集编辑、姿态编辑、动画时间轴、视频生成、内置图生图和局部重绘、断线自动恢复、实时中间图预览。当前显示的是采样进度及最终图片。
