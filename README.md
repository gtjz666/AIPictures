# AIPictures

Windows 本地游戏美术创作工具，Python + PySide6 独立界面。当前操作以[完整动画与素材导出](docs/VIDEO_FIRST.md)和[模型选型与实测](docs/MODEL_SELECTION.md)为准。

## 当前生成路线

- **文字生图**：Z-Image Turbo原生理解中文，支持人物、物件、场景、不同画风与视角。另有经过本机验收后才启用的FLUX.2 Klein快速路线；不会因为更快就宣称每项提示执行都更好。
- **自动分流**：默认无参考用Z-Image、有参考用FLUX独立参考编辑，界面显示实际引擎。移除参考回到文字路线，手选引擎不被替换；Z-Image小幅重绘另可手选。SDXL普通入口已退役。[路线、同图比较与使用](docs/REFERENCE_ROUTES.md)。
- **完整动画**：MiniMax H3独立环境，提示词与可选参考图直接生成完整片段。走路、跑步、跳跃、下蹲、攻击、待机只是可编辑文字模板，也可自行描述动作。**旧骨骼与Wan生成入口已退役**，没有H3时明确提示不可用，不自动切回旧路线。
- **游戏素材**：动画先完整循环预览，再由用户自主勾选源帧，一键导出精灵PNG+JSON或独立PNG。导出时可选透明背景，先生成RGB再去背景，不混帧、不自动选择关键帧。
- **用户自带API**：单图支持OpenAI Images兼容与Gemini原生接口。提示词整理是额外可选调用，默认关闭；聊天Key不等于生图权限。[接入说明](docs/API_GENERATION.md)。

LoRA已停用，不自动选择或重新下载。现有图像模型直接读取文字/参考图，不额外安装Qwen3.8-27B分析模型。新图像模型有组件和真实验收双重检查，下载完成本身不代表可用。

## 使用

1. 在项目目录运行`run.bat`。单图连接本机ComfyUI；H3使用自己的已验证独立环境，不要求用户手动编辑工作流。
2. 主区选择“单张图片”或“动画制作”。没有参考图时保持空白；点“＋参考图”立即显示所选图片，“移除”取消绑定。不会自动放入旧角色图。
3. 在唯一正向框描述外观、场景与动作，反向框填写希望避免的内容。模板可直接修改，不暗中强制骨骼动作。参考编辑时明确哪些要改、哪些要保留。
4. 点生成，左下任务名、百分比及经过时间显示状态。完成图片可点击放大；完整动画默认循环，可暂停、逐帧查看。
5. 动画点“选帧与导出”，勾选需要的源帧，选择精灵图或独立PNG。需要抠图时勾选透明背景；默认没有预选帧。

种子默认每次随机；本次实际种子可查看、复制/复用，结果和导出记录真实值。随机并不保证最佳，未知种子不伪造。

浅色两栏界面，左侧按钮打开小设置窗口，右侧预览和提示词。固定模型的无效采样参数不占用界面。普通控件不显示长悬浮说明；CFG等难参数保留简短解释。消息、队列、日志默认隐藏，按`Ctrl+J`打开。

结果默认是缓存，主动“另存为/导出”才选地址。“生成记录与缓存…”可删除未保存缓存；正在处理的素材受保护。历史Wan/骨骼成品仍可预览和选帧导出，但旧任务不能重新提交。

## 像素素材与后处理

独立CLI：`python -m sprite_pipeline --help`，支持snap、normalize、palette、assemble、validate、config及run。像素捕捉→统一画布/锚点→共享调色板→精灵图→验收，输出可逐像素切片回读的metadata。[配置与验收](docs/SPRITE_PIPELINE.md)。

不使用时间混合、FXAA/TAA/DLSS或全局自动抗锯齿。像素预览用最近邻，不默认缩放角色。透明处理只改Alpha，保留原生RGB。PNG支持完整透明；GIF二值透明有限制。当前原生生图默认不开额外超分。

## 安装、模型和稳定性

桌面依赖见`requirements-lock.txt`，`setup.bat`创建独立Python3.13环境。复用自己的ComfyUI，不覆盖原工作流。H3有独立安装/验收步骤，见[动画说明](docs/VIDEO_FIRST.md)。模型、参考图、生成记录、环境和Key均不上传Git。

FLUX可选组件安装：`python -m tools.prepare_flux_klein --comfy-root "YOUR_COMFY_ROOT"`，复用已有且SHA一致的Qwen3编码器，只新增扩散模型与VAE。需实际生成验收后才注册，不能手工把文件存在等同于验证。[模型比较与来源](docs/MODEL_SELECTION.md)。

管理Wan权重只按安装收据、大小和发布SHA逐文件删除。本轮按用户要求退役核验一致的SDXL主模型，硬链接去重后释放约14.04GB；原ControlNet、IP-Adapter、姿态检测、CLIP Vision、图片和工作流保留。旧SDXL检查点/Wan/骨骼安装器不再安装这些退役权重。

进度连接中断时按原任务标识继续查询，不自动重复提交；Windows短暂占用进度文件时重试原子保存。H3取消/关闭只处理自己的进程树，不重启共享后端。其他程序正在使用GPU时，实际速度会变化。

FLUX/Z-Image蒸馏CFG1路线的反向内容是自然语言软约束；生成仍可能有手部、服装、视角或身份细节偏差。有限测试通过不代表百分之百准确。H3和其他模型的许可各自有效；游戏资产使用/分发前需核对模型原始条款。

## 验证与接续

```powershell
python -m pytest -q
$env:QT_QPA_PLATFORM='offscreen'
python -m tests.live_h3_image_choice
python -m tests.live_video_first
python -m tests.live_manual_frames
```

[中文通用测试提示词](docs/GENERAL_TEST_PROMPTS.md)、[API说明](docs/API_GENERATION.md)、[模型选型与本机对照](docs/MODEL_SELECTION.md)。骨骼、LoRA与旧Wan资料保留为历史研究，不是当前操作指引。数据集训练、完整时间轴编辑等后续阶段尚未作为可交付功能实现。

更换coding agent：先读[AGENTS.md](AGENTS.md)、[交接说明](.agent/README.md)和`.agent/STATE.local.md`。不迁移账号、订阅和Key，也不自动启动其他agent。

仓库：[gtjz666/AIPictures](https://github.com/gtjz666/AIPictures)。
