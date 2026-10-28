# 本机验证记录

## 2026-10-28：预填中文通用提示词

正反词预填支持单图 / 动画、参考图 / 纯文字四种组合，全部能映射到现有中文词表，没有未识别默认词。真实 Qt 检查覆盖启动预填、未编辑内容随类型更新、用户已编辑内容跨模式保留、一键恢复两栏，以及提示词恢复不改变手选 LoRA。默认只提供构图与质量约束，不写死角色外观；文字模式需补充目标外观。此改动未增加模型下载，也未为界面文本修改重复运行 GPU 推理。

## 2026-10-28：手动风格 LoRA、空参考与抗锯齿

安装 10 款 SDXL LoRA（1,296,522,988 字节），覆盖动漫、写实、卡通、插画与像素；逐文件与固定版本的 Hugging Face LFS SHA-256 核对。另安装官方动漫 / 通用 Real-ESRGAN，共 85,000,524 字节，核对发布大小并记录 SHA-256。全部新增 1,381,523,512 字节，模型位于 ComfyUI models，不修改旧工作流或基础模型。完整来源、许可标签、用法见 [模型说明](LORA_MODELS.md)。

45 项单元测试通过。真实 Qt 检查通过：从已有 character_id 设置启动仍不加载参考图片、不创建参考副本，用户选图后显示完全相同的图片，移除后预览和绑定留空；手动类别筛选不自动加载第一项，提示词改为其他风格也不改变所选 LoRA。验证将 LoRA 接到已有 IP-Adapter 工作流的 model / clip 上游，保留 VAE 和原模板。动画来源切换后控件按实际适用范围启停。

10 款 LoRA 分别做相同提示词、种子、16 步及 512×640 的 0 强度 / 推荐强度实际出图，共 20 次，均确认输出变化，约 175 秒。写实 / 水彩加入手动选择对应的静态风格短语后，又完成 4 次对照。证据 data/style-models-acceptance.json、data/style-refinement-acceptance.json；对照图保存在各测试缓存目录。部分样图出现多视图或不理想构图，这不属于完全视觉质量通过，也没有宣称 LoRA 能修复所有生成错误。

真实桌面完成“参考图留空 → 选手绘动画 LoRA → 选动漫高清修复 → 768×1024、24 步 SDXL → 本地透明处理 → 显示及保存”，记录 data/style-image-acceptance.json。初次 512×640 动漫滑杆测试链路也运行成功，但产生多视图 / 道具，保留为 data/style-image-initial-functional.json。后一张手绘样图单人、画风与边缘较好，仍有脚部裁切，未把构图视作完全验收通过。

两款 Real-ESRGAN 分别对已缓存的人物与黄色卡通原始帧实际运行，确认两图返回顺序及 768×1024 输出，记录 data/quality-models-acceptance.json；未重跑 Wan 采样。预览检查验证原图放大始终使用平滑变换，且可切回像素原样；高分屏按逻辑 / 实际像素比例绘制。Alpha 轮廓测试确认边缘增加半透明覆盖、远处背景及真正空隙保持 0、内部 RGB 不变。PNG 支持软边，GIF 二值透明的阶梯限制仍存在。

文字动画的前置 SDXL 图确实接收 LoRA；Wan 图中不含 SDXL LoRA。当前只对其图结构及前置单图做回归，本轮未重新完整运行加 LoRA 的 Wan 行走视觉验收。已有动画画质问题与此限制仍按下方记录保留。

## 2026-10-28：连续行走与透明背景

本轮保持 ComfyUI 源码、已有工作流和旧 SDXL 模型不变。下载并校验 Wan2.2 I2V 14B FP8 的高 / 低噪声模型、UMT5 编码器和 Wan2.1 VAE，共 35,579,207,879 字节，安装位置为 `D:\Local Comfy\ComfyUI\models`；逐文件 SHA-256 校验成功，记录在 `data/wan-model-installation.json`。

BiRefNet general 已安装并启用，972,666,916 字节，位于 `D:\ComfyModels\matting\models\birefnet-general\birefnet-general.onnx`，MD5 为 `7a35a0141cbbc80de11d9c9a28f52697`，与 [rembg 模型定义](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/birefnet_general.py)一致。旧 IS-Net 权重保留，设置在 `data/background-settings.json`，安装与对比记录在 `data/background-model-installation.json`、`data/birefnet-comparison/comparison.json`。

真实推理与视觉检查分别记录：

- 黄色卡通参考图：通过真实 Qt 入队，20 步、33 张原始连续帧，输出 8 张不同的透明 PNG、精灵图和 GIF，收到 20 次采样进度；不使用人体检测、ControlNet 或肢体复制。原始端到端测试约 682 秒。最终采用原生 VAE 连续解码，未见先前周期性闪帧和双眼重影。结果在 `data/animations/20261028_123718_6d9c75ca`。
- 粉发红衣人物：真实 14B 推理约 653 秒；整段生成取代旧衣袖拼接。用 BiRefNet 复用原始 RGB 重做透明帧，白色靴子恢复，腿间空隙仍透明。对比点原始 RGB `[238,233,234]` 不变，旧 Alpha 0、新 Alpha 255。结果在 `data/animations/20261028_125126_27785417`。
- 纯文字角色：输入 `黄色卡通小恐龙，白色肚皮，大眼睛，全身，侧视`，没有“动画 / 走路”关键词；界面选择走路后，先生成角色图，再真实运行 14B。约 603 秒，收到 20 次视频采样进度。BiRefNet 重做 8 帧后，肚皮和嘴部不再被误删，PNG / GIF 外围透明、8 帧均不同、Qt 播放和图片操作通过。本次机器高负载下透明重做约 580 秒。**功能与前景分割通过，完整精灵成品质量未通过**：仍有脚趾形状变化、源角色图自带的白色描边和地面阴影；这些已经存在于生成 RGB 中，不是抠图漏色。结果在 `data/animations/20261028_133436_072961cc`，分项验收分别保存，未把功能成功记成视觉成功。

解码问题曾做同一 latent 的受控对比：时间分块大小 16 的解码在第 12 / 24 帧附近引入明显变化；原生解码消除这组闪变。对比在黄色卡通缓存的 `decode-comparison` 子目录，没有重新采样或更换角色来掩盖问题。

36 项单元测试通过。真实 Qt 检查通过：浅色布局、并排提示词、可复用设置弹窗、生成类型优先于提示词动作、参考 / 文字来源切换、图片原尺寸放大、动画点击不放大、隐藏输出面板、缓存清理与外部保存文件保留。证据在 `data/preview-controls-acceptance.json`、`data/settings-cache-acceptance.json`。最后一次预览检查直接加载新的文字动画缓存。

最终配置的 CPU 实际分割检查通过：原始 RGB 逐像素保持，白色鞋面保持不透明，背景角落为 0。Qt 计时器响应 5,158 次；销毁分割会话后，该进程驻留内存从约 8.99GB 降到 0.39GB。检查约 108 秒（机器同时有其他较高负载），记录在 `data/foreground-live-acceptance.json`。长批次内存池与负载曾显著拖慢处理，现先按缩略图选循环帧，仅处理导出的 8 / 16 帧，并每 4 帧释放模型会话；不把短测约 8 秒 / 帧视为稳定速度承诺。

当前 8188 服务没有枚举到旧版 SDXL Pose ControlNet 权重；旧版骨骼入口会明确报告缺失，普通参考图单张重绘会跳过可选姿态，默认 Wan 连续动画不依赖它。没有把模拟的模型可用性检查当作真实生成通过。16 帧选项有结构覆盖，未单独运行完整 14B 视觉验收；长时间压力、复杂遮挡、多主体和所有角色种类未验收。AI 仍可能改变鞋型、细小衣饰、动作幅度和循环接缝，负向提示词不能保证消除这些问题。手动骨骼编辑尚未实现。

所有原图、帧、参数、模型和测试缓存均留在本机并由 Git 忽略；仅源码、测试和文档上传仓库。

## 初始阶段与历史验证

日期：2026-10-26。

环境：Windows，RTX 4080 Laptop GPU，12282 MiB 显存，约 32GB 系统内存。软件独立 Python 3.13.14、PySide6 6.12.0。既有 ComfyUI 0.20.1 位于 `D:\Local Comfy\ComfyUI`，其独立 Python 3.13.12、Torch 2.10.0+cu130。服务监听 127.0.0.1:8188。

已发现基础模型 `sd_xl_base_1.0_0.9vae.safetensors`；外部路径另有 IP-Adapter 权重。未发现可测试 FLUX、LoRA、Pose ControlNet 权重。不以现有节点存在推断权重完整。

已通过：

- 4 项结构/兼容测试：LoRA 连接、尺寸验证、本地地址限制、空成功响应解析。
- 真实桌面调用：768×768 SDXL、20 步，收到 20 次 progress 事件，界面计时器持续响应，PNG 下载、QPixmap 最终预览、任务参数和工作流保存成功。机器证据在 `data/acceptance.json`，截图在 `data/acceptance-desktop.png`。
- 真实按任务取消：在首个采样进度后按 prompt_id 取消，无全局 interrupt。证据在 `data/cancellation-test.json`。
- 真实队列与失败恢复：先提交一个不存在的 checkpoint，再加入两张 256×256、2 步测试任务，最终状态依次为 failed、completed、completed。证据在 `data/queue-test.json`。
- Python 编译检查通过。
- 内嵌节点编辑真实链路：加载 7 节点 SDXL 图，在编辑器修改提示词与步数，保存副本后重新打开，核对参数、连接及节点位置，点击软件运行按钮生成 512×512 图片，收到 4 次采样进度，图片预览及 `editor_workflow.json` 保存成功。证据 `data/editor-acceptance.json`、`data/editor-roundtrip.json`、`data/workflow-editor.png`。
- Local Comfy 移植：三份活动 UI 工作流逐份在编辑器加载并导出 API，核对模型/输入图名称、原提示词、尺寸、采样参数和所有连接。基础图使用原始 768×1024、28 步配置真实生成成功，收到 28 次采样事件。源文件及其副本 SHA-256 相同；重复导入保持 3 个条目。另两份仅验证加载/结构，不在权重和图片缺失时排队运行。证据 `data/migration-acceptance.json`。修复了编辑器启动恢复旧标签页与首次导入之间的时序问题。
- 新增依赖缺失和悬空连线检查测试，总计 6 项单元测试通过。
- 对话链路：选择已移植的基础模板，在聊天框输入与原角色描述不同的新提示词，实际工作流中的 CLIP 输入、采样参数正确覆盖，768×768、24 步生成成功；将结果作为参考图上传后再生成，确认输入文件与原图逐字节相同、真实 VAEEncode 路径接入、重绘幅度生效，高级编辑器导出的文本/参考输入与实际任务相同。两张图片共收到 48 次采样进度，源文件 SHA-256 不变。证据 `data/chat-acceptance.json`。
- 参数绑定单元测试覆盖模板不可变、正负提示词分离、图生图注入、IP-Adapter 参考图不误替换姿态图，以及多提示词歧义拒绝，总计 10 项测试通过。
- 蓝发侧视基准 v3：用本次图片创建独立参考、18 关节人工标注骨架、站立及伸手草案，未改动旧仓库。SDXL + IP-Adapter PLUS + CLIP Vision + 分块 VAE，768×1024、28 采样步、0.30 重绘完成真实生成。检查左侧 Inspector、文件弹窗、骨骼叠加窗口和缺失 ControlNet 时不提交。证据 `data/character-acceptance.json`、`data/character-studio.png`、`data/character-skeleton.png`。
- 初次非分块解码时历史查询超时，但 ComfyUI 随后完成；已按原 prompt_id 回收图片并保留原错误记录。分块版本实际运行通过；增加“监控超时不重复提交”单元测试。当前共 14 项单元测试通过。
- 2026-10-27：当前 8188 服务改为 Comfy Desktop 的共享模型/输入目录，已识别所需 SDXL Pose ControlNet。重新上传角色参考和站立/伸手条件图，逐字段核对原 API 与前端导出内容，保存 UI 副本并登记工作流库。站立工作流以 ControlNet + IP-Adapter、768×1024、28 步实际执行成功；伸手尚未单独出图。原 API 源文件哈希不变，先前角色配置已备份。测试图存在白袜/鞋型变化，不等同于身份一致性验收通过。证据 `data/controlnet-import-acceptance.json`。

限制：未测试不存在的模型管线；LoRA、FLUX、自定义训练/视频工作流未进行真实生成验证。手动另存文件对话框与长期压力测试尚未自动验证。断线后不自动重提交；任务可能继续在 ComfyUI 执行，需通过保存的 prompt_id 核查。当前资源管理是服务端模型枚举与卸载，不含模型下载和删除。

首次 ComfyUI 启动日志写在原聊天工作目录 `C:\Users\qcy_2\Documents\ChatGPT\生图软件`；后续通过项目 start-comfy 启动时日志位于本项目 data/logs。早期环境探测曾在原聊天目录创建临时 .venv；正式软件与独立环境均在桌面 AIPictures，AIGAMING 没有修改。
