# MOSS 接入评估（2026-10-31）

结论：将 MOSS-Image 列为单张生图与参考图编辑的候选，暂不替换现有动画后端。以下是资料及兼容性核查，不是本机出图对照；本轮未下载 MOSS 权重、未安装插件、未升级共享 ComfyUI。

## 确认模型

近期相关发布是 [OpenMOSS/MOSS-Image](https://github.com/OpenMOSS/MOSS-Image)，2026-10-16 发布 Base 与 SFT，5B 图像主干，支持自然语言、标签和 JSON 布局。另有 [MOVA](https://github.com/OpenMOSS/MOVA) 音视频生成、MOSS-VL 视觉理解，名称相近但用途不同。

| 目标 | 判断 | 依据与未解决项 |
| --- | --- | --- |
| 动漫/写实角色、物件、背景、文字布局 | 值得对照测试 | Base/SFT 面向文生图；SFT 作为首个候选，不能凭展示图认定优于本项目现有模型 |
| 参考角色换服装、场景、画风或视角 | 值得另测编辑分支 | [Moss-Image-Edit](https://huggingface.co/chinoll/Moss-Image-Edit) 已提供编辑 LoRA，支持单图和多参考；不能将基础 T2I 工作流误当作参考图编辑 |
| 动画连续帧、骨骼精确约束、鞋子与配色跨帧一致 | 目前不作为替换依据 | 文生图或编辑单帧没有自动获得时序一致性；基准图可作为现有动画流程输入，但仍需逐帧验收 |
| 颜色区域与深度控制 | 研究候选 | [作者模型卡](https://huggingface.co/darask0/MOSS-Image-color-depth-control) 明确颜色是区域 ID，不是原图固有色；不是“读取原色填色”方案，也不是 OpenPose 的直接替代 |

[官方用户指南](https://github.com/OpenMOSS/MOSS-Image/blob/main/USERGUIDE_ZH.md)支持中文，但仍推荐英文作为训练覆盖最多的语言；不能宣称仅换模型就解决中文准确率。其 GIF/参考生成的后训练说明不能当作已交付的时序权重。编辑 LoRA 是另一项已经发布的社区成果，应分别判断。

## 本机接入条件

本机共享后端为 ComfyUI v0.20.1；只读查询 `CLIPLoader` 没有 `moss_image` 类型，源码也没有 MOSS 实现。当前环境不能直接放入新权重就运行，亦不能复用 Wan 的 UMT5 编码器、VAE 或 SDXL 风格 LoRA。

[官方 ComfyUI 接入说明](https://github.com/OpenMOSS/MOSS-Image/blob/main/comfyui/README.md)要求包含原生支持的核心修订（`e087d8f6` 或以后），使用 MOSS 专用文本编码、匹配 VAE 和工作流。原生与旧插件的时间步倍率不同，不能沿用旧插件的 ModelSamplingSD3。独立 Diffusers 路径与原生 Comfy 路径的依赖要求也不同；不向现有环境直接执行全量依赖升级。

[编辑项目接入说明](https://github.com/Chenkin-x/ComfyUI-Moss-Image-Edit/blob/main/README.en.md)给出独立的原生 API 要求，并记录了 Windows 8GB 显存设备的量化编辑实例；这是作者环境的结果，不是本机验证。底模采用 Apache-2.0，编辑项目代码采用 GPLv3，各组件许可分别保留，不将底模许可扩展到全部代码和权重。

首轮原生测试应使用项目作者推荐的 Euler、约 50 步、CFG 3、Shift 5、SLG 22 等模型专用配置，保留 FP32 VAE；不可照搬 Wan 的 CFG 1，也不先用少步蒸馏或预测加速器比较最终质量。编辑分支另按其发布工作流测试，不能混合两者参数。官方仓库还列出针对色带的社区 LoRA，这意味着新模型也需要检查色带和细节变化，不默认开启未经对照的修补。

## 下载体积核查

从 [Comfy-Org 发布文件](https://huggingface.co/Comfy-Org/MOSS-Image/tree/main)读取文件大小，仅获取 JSON 元数据，没有下载权重。单位为十进制 GB，包含单个 SFT 主干、文本编码器和 small VAE，不含 LoRA：

| 组合 | 磁盘文件合计 |
| --- | ---: |
| SFT BF16 + Qwen3.5-9B BF16 + small VAE | 约 29.72 GB |
| SFT INT8 + 编码器 INT8 + small VAE | 约 15.41 GB |
| SFT INT8 + 编码器 W4A8 + small VAE | 约 13.01 GB |

编辑 LoRA 另约 0.30 GB。快照保存于 `data/research/moss/20261031/comfy-model-files.json`。文件体积不等于运行显存；12GB 显存需要实际验证量化格式、组件卸载、参考图缓存和分辨率，不能按“5B”推断整套可常驻显卡。精度不同的结果也需单独评估。

## 决策与下一次对照

先完成当前五种动画的真实验收。若推进 MOSS，先用隔离的测试环境验证，避免修改正在服务的共享环境；产品最终仍选择一套经过验证的后端。测试成功前不新增默认模型、不改用户工作流。

对照至少覆盖：动漫与写实角色、道具、俯视/等距场景、自然背景、含中文文字的布局；每类使用多组固定种子与相同画布，保存实际参数。编辑加入侧视转正面、换姿势、换服装和保留颜色测试，包含用户提供的不同体型参考，不只看单张成功样例。

分别记录提示词遵循、角色身份/服装/颜色、局部结构、文字与构图、失败率和实际耗时。参考图只在本地测试，不为试用在线服务上传用户图片。单帧胜出后可作为可选生图/编辑模块；若用于动画基准图，再检查最终完整周期，不能用静态图成绩代替动画稳定性。
