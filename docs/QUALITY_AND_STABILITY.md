# 单图质量、稳定性与视频转精灵帧

本轮针对无参考图的人体/主体混叠、中文理解、模型加载耗时和操作入口作修改。自动检查通过不能代替美术验收，反向提示词也不能保证消除错误。

## 操作

运行 `run.bat`，使用同一个本地 ComfyUI 地址。

1. 在主画面上方选择 **单张图片 / 动画序列帧**；动画动作直接在旁边选择，不需要在提示词中重复“生成动画”。
2. **模型与画面… → 图片引擎**：无参考图可选 Z-Image Turbo，直接填写中文；需要参考图编辑或已有风格 LoRA 时选择 SDXL。模型文件齐全且后端支持对应节点时，Z-Image 才能选择。添加参考图或绑定已有 SDXL 工作流时，会明确切换至 SDXL 路线，不把参考图静默丢弃。
3. **SDXL** 优先提供已安装的 Juggernaut v9，保留原基础模型和手动风格列表。默认单图为 1024×1024、30 步、CFG 5.5；人像可选 832×1216。不同模型/LoRA 的推荐参数仍以各自说明为准。
4. 正反提示词并排显示，不预填强制人物、侧视或站姿。原生 Z-Image Turbo 使用官方 CFG 1 路线，反向栏转成自然语言排除要求，**没有 SDXL 式独立负向引导的保证**。原文和实际工作流均保留。
5. **动画 → 自定义动作** 默认显示 AI 自由动作，动作说明直接可填。需要逐帧控制时选择骨骼编排；六种预设仍走完整骨骼序列。预设与文字姿势冲突会明确提示，外观整理会剔除冲突姿势，单张图片不受这个过滤影响。
6. **生成记录与缓存… → 导入视频制作动画帧…**：选择本地动作视频或 GIF、8/16 帧、FPS、是否提取循环和透明背景。可选“关键姿态优先 + 源过渡帧”或“均匀取帧”。原生画布解码，先生成/解码 RGB，再处理 Alpha，输出独立 PNG、精灵图、GIF 和来源记录。不需要启动 ComfyUI；透明分割需要现有本地模型。

普通按钮和明显字段不再附长篇悬浮文字。LoRA、采样、参考权重和引擎等难参数保留帮助。动画隐藏单图参考策略，切回单图恢复原画布和采样设置。消息/日志仍默认收起，Ctrl+J 打开。

## 模型与原始工作流来源

- [Fooocus 默认配置](https://github.com/lllyasviel/Fooocus/blob/main/presets/default.json) 采用精调 SDXL、适当 CFG 与原生画布。这里借鉴选用合适基础模型和隐藏复杂设置的方式，没有声称复制 Fooocus 的全部内部处理。
- [InvokeAI 界面](https://invoke.ai/features/workflows/editor-interface/) 与[开源仓库](https://github.com/invoke-ai/InvokeAI)：任务入口明确、画布居中、按当前任务呈现设置。本项目继续使用独立 PySide6，不引入整套 Web 前端。
- 检索了[秋叶作者账号](https://github.com/Akegarasu)，本轮没有找到可核实作者来源、直接适用本任务的独立 ComfyUI 工作流 JSON，因此未使用来源不明的搬运整合包。
- [Juggernaut v9 模型卡](https://huggingface.co/RunDiffusion/Juggernaut-XL-v9)：照片/通用 SDXL 可选路线；仍可能偏向写实，不能取代所有动漫专用模型。安装固定 revision 和 SHA256，使用者仍需遵守发布方许可及服务分发条件。
- [Z-Image 官方 ComfyUI 工作流](https://docs.comfy.org/tutorials/image/z-image/z-image-turbo)、[原始项目](https://github.com/Tongyi-MAI/Z-Image)、[Comfy 分拆权重](https://huggingface.co/Comfy-Org/Z-Image-Turbo)：6B 扩散模型，原生中英文，独立 Qwen3 文本编码器。当前实现用 BF16 扩散模型、官方 FP8 mixed 编码器、9 步 Euler/simple、CFG 1，不混用 SDXL LoRA。Apache 2.0；不等同于 Qwen-Image-2.1，也不是聊天 LLM 直接画图。

GPT 可借鉴的是公开的 **需求整理 → 生成或参考编辑 → 以结果继续编辑**，见 [OpenAI 图片接口说明](https://developers.openai.com/api/docs/guides/image-generation)。现有“继续创作”将结果作为下一次参考，API 整理是可选调用。私有 GPT 生图权重/内部推理过程没有被本地复刻；本地一致性仍取决于实际图像或视频模型。

## Qwen-Image-2.1 / MiniMax H3 的评估

| 候选 | 已核实能力 | 本轮决定 |
|---|---|---|
| Qwen-Image-2.1 | 官方统一文生图/编辑、原生 RGBA，多图参考；视觉组件 7B，编码器另计 | 保留候选，不替换当前工具。当前后端缺少对应新节点；发布的研究许可限制商业使用，游戏生产场景需另行许可 |
| MiniMax H3 | 开放基础权重，图生视频、参考视频、首尾帧控制；基础扩散 33B，文本编码器也很大；官方工作流要求较新 ComfyUI | 不把它冒充已接入或保证更好的精灵动画。当前后端 0.20.1，需独立兼容性/输出验收。原始社区许可在适用地区允许有条件免版税商用，不能笼统认为所有商用都须付费授权。此次不覆盖现有环境 |

来源：[Qwen 模型卡](https://huggingface.co/Qwen/Qwen-Image-2.1)、[研究许可](https://github.com/QwenLM/Qwen-Image-2.1/blob/main/LICENSE)、[H3 官方仓库](https://github.com/MiniMax-AI/MiniMax-H3)、[H3 模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)、[Comfy H3 版本及商用说明](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)。[FreeVideo/VDN](https://github.com/FlashML-org/FreeVideo) 提供低显存优化方向，但没有在本机验收，不用其宣传数字推断本机速度，也不会绕过基础模型许可。

**许可更正（2026-11-01复核）**：Comfy教程对本地商用的概括与MiniMax原始条款不一致。应核对[原始社区许可证](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)和[MiniMax官方FAQ](https://design.minimax.io/h3)：在适用地区允许有条件免版税商用；年营收超过2000万美元需额外书面授权，使用模型的商业产品/服务有界面标识等要求。原许可还排除美国、欧盟、英国、韩国，并对这些地区使用/展示输出等有限制。因此既不能一概说必须购买许可，也不能视为Apache式全球自由商用。软件集成与游戏资产全球发行应分别核对条款。没有实测证明H3在本项目的角色细节/循环方面优于Wan；低显存优化可行性和画质应单独验收。

即使模型能输出视频，也不自动等于独立游戏素材：固定镜头、完整角色、手脚接触、配色和周期接缝都需要验收。因此精确动作继续保留骨骼路线，自由动作和视频转帧单独使用。没有下载 Qwen-Image-2.1 / H3 权重，未发起付费 API 请求。

## 中文转英文

SDXL 可主动勾选 **中文转英文 · 本地单图**，默认关闭。小型 CPU 译器在独立进程运行，复用已有 Comfy Python，不在桌面环境另装 Torch。艺术词先做明确词表保护，只翻剩余中文，英文保持原样。`translation.json` 保存原文和生效文本；取消翻译不会提交生成任务。

实际使用 [Helsinki-NLP/opus-mt-zh-en](https://huggingface.co/Helsinki-NLP/opus-mt-zh-en)，CC BY 4.0，约315MB。最初直译把“动漫女孩”“五官”理解错误，因此没有采用裸翻译结果；现有艺术词表已覆盖这些案例。复杂叙述仍可能错译，可以关闭后输入英文或用原生中文模型。翻译会增加少量 CPU 时间，不能保证端到端更快。

翻译**不会减小既有图像权重，也不能替换其训练时的文本编码器**。它能避免为了翻译部署另一个大型聊天模型；这与减少扩散模型大小是两回事。Z-Image 和云端图片 API 直接接收中文，不再重复运行译器。LoRA 始终由用户手动选择。

## 稳定性

- 单一后端、GPU 串行。断线/读取超时继续查原任务 ID，不重发生成请求；原始潜变量先保存，再分阶段解码。关闭窗口不等待 GPU 线程退出，也不杀其他客户端任务。
- 可选运行节点在原官方 Wan 条件编码前释放已完成的文字/图像编码器，保持官方编码计算、尺寸、精度和条件数量不变，显示各次条件编码阶段。
- 条件编码超过 5 分钟显示异常等待提示；保留任务，不把等待当完成，也不自动重跑。CUDA 内部长操作仍可能延迟取消，不能承诺立刻打断每个内核。
- 启动器使用 Comfy 自带的 `--disable-dynamic-vram` 兼容加载方式；它改变权重加载策略，不降低分辨率或精度。已打开的外部后端会被复用，不强行改其启动参数。需要应用启动参数时，先确认任务结束，再重启同一实例。

本机原生中文3张真实出图：动漫全身111.43秒、写实肖像107.90秒、单个道具92.18秒（含本次加载/解码）。对照动态加载用394.72秒只走完前2步后取消，兼容加载完成同图；这不是所有硬件的通用速度承诺。SDXL base/v9四类共8张实测，对人脸/重复主体有改善，但动漫双手插兜仍未遵从；Z-Image本次中文全身图实现了手臂下垂可见。

更新后的兼容模式，完整33帧骨骼条件准备53.06秒（VAE19.2秒），自由动作条件准备26.25秒（VAE8.3秒）。仅验证条件准备，不是新整段动作采样。

原异常任务停在姿态 VAE 编码超过45分钟。同33帧同画布的新独立编码实测17.3秒；完整条件准备实测64.13秒，其中三次 VAE 总计17.5秒。证明原长等异常，**这些测试没有运行14B扩散采样，不能据此宣称整段动画只需一分钟**。这也没有证明所有卡顿都是同一显存管理缺陷。

## 视频循环与资产约束

视频导入支持 MP4/MOV/WebM/MKV/AVI/GIF，有效时长不超过30秒、文件不超过2GB。使用 PyAV 解码源帧，按真实时间采样；不缩放 PNG 内容，不做 FXAA/TAA/DLSS、光流插帧、时间混合或首尾交叉淡化。

关键姿态捕捉通过轮廓与画面变化曲线寻找转折，再从时间间隔较大的区间补入真实源过渡帧，直到达到8/16帧；每帧标记关键姿态/过渡帧、源时间和索引，导出的 animation.json 保留来源。它是画面变化估计，不等于人体关节检测；镜头运动和背景变化会干扰，不能从一张静态图恢复未出现的动作。固定FPS回放会改变非均匀取样的局部节奏，需要严格均匀时序可选“均匀取帧”。

循环选择比较真实帧的轮廓、颜色和运动方向，选首尾较近的一段，排除重复终点。指标只用于选帧，不重写像素；接缝大、方向差异或动作很小时给警告，`guaranteed_seamless=false`，不会把任意片段强称无缝。跳跃/攻击等单次动作请取消循环。

源 RGBA 已有有效透明通道时保留，其他画面在解码完成后分割；处理前后 RGB 必须相同。GIF 是便携预览，颜色/透明度有限；游戏资产使用 PNG 序列或精灵图。像素画另用现有 `sprite_pipeline`，不对所有手绘角色强制量化。

## 安装与复测

现有电脑已安装权重，无需重复下载。新电脑按需执行，下载工具不在软件启动时自动拉取所有模型：

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
& .\.venv\Scripts\python.exe -m tools.prepare_quality_models --models 'D:\ComfyModels' --translation-python 'D:\Local Comfy\ComfyUI\.venv\Scripts\python.exe'
& .\.venv\Scripts\python.exe -m tools.prepare_zimage_models --comfy-root 'D:\Local Comfy\ComfyUI'
& .\.venv\Scripts\python.exe -m tools.install_runtime_nodes --comfy-root 'D:\Local Comfy\ComfyUI'
```

运行节点只安装到自己的 `custom_nodes/AIPicturesRuntime`，变更已有本节点会备份，不修改 Comfy 核心或原工作流。安装后在空闲时重启现有后端，回软件刷新模型。小译器所用独立 Python 需已有 Torch、Transformers、SentencePiece；不兼容时先建独立环境，不覆盖原推理依赖。

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
$env:QT_QPA_PLATFORM='offscreen'
& .\.venv\Scripts\python.exe -m tests.live_platformer_controls
& .\.venv\Scripts\python.exe -m tests.live_animation_modes
& .\.venv\Scripts\python.exe -m tests.live_quality_controls
```

实际耗 GPU 的复测工具是 `tools.verify_single_image_quality`、`tools.verify_native_quality`、`tools.verify_runtime_conditions`。先看已有结果和队列；使用新目录，已有回执只恢复同一任务，不重提。离线视频 CLI：

```powershell
& .\.venv\Scripts\python.exe -m tools.import_animation_video '你的动作.mp4' --output 'out/video-sprites' --frames 8 --fps 8 --loop --transparent --sampling keyframes
```

实际Qt窗口→翻译→本地SDXL→预览/保存已打通，原文和有效英文可核对；离屏界面测试的总耗时包含离线环境加载和事件轮询，不用于承诺日常速度。既有AI素材编码成保留Alpha的无损MKV，再关键帧捕捉/源过渡帧补齐、PNG和精灵图导出共4.82秒，逐像素回读通过；不是新生成的H3视频。

测试覆盖本地协议/UI、关键姿态极值捕捉、8帧GIF直接导入、帧循环、真实无损视频解码、PNG/精灵图逐像素回读、艺术词翻译保护、运行节点先释放后调用。实际生成图片仍需查看；手指、遮挡和多角色交互没有达到接近100%的准确率。真实结果与耗时以本机验收目录和生成记录为准，不随 Git 上传。

最后回归：271项测试、7项子检查通过；六种预设与平台动作Qt检查通过。新增关键帧/GIF、动画预览/ZIP和Alpha保护检查均通过。
