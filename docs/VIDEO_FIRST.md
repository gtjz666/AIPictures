# 完整动画 → 游戏素材帧

当前主流程是 **提示词 / 可选参考图 → 自由动作 → 完整动画预览 → 用户选择拆帧**。动画只使用已验证的MiniMax H3，旧骨骼与Wan入口已退役，不要求逐帧拖关节。LoRA 功能已停用；画风、主体和修改由描述及参考图决定。

新增[动作参考](MOTION_REFERENCE.md)：动画模式下用“＋参考动画”导入视频/GIF，或“＋动作帧”导入PNG序列并填写FPS。它们提供动作与节奏，“＋角色 / 风格图”提供主体外观，两者分别入队冻结。无动作参考时本页原有路线继续使用。专用Ref2VA环境未验证时明确禁用此新生成线路，不回退到旧骨骼或有重影的实验线路。

## 软件操作

1. 运行 `run.bat`，选择“动画制作”。**正向提示词统一填写外观、场景和动作**；反向提示词仍单独并排。动作模板仅向正向框填入可编辑文字，不再有另一份隐藏动作要求覆盖用户内容。切回单图时恢复单图草稿。
2. 在“角色与生成…”选择参考图或仅文字，以及片段时长。动画引擎为MiniMax H3。无参考图时界面留空。生成参数默认“每次随机”；原来的`-1`只是内部随机标记，不是固定种子，也不代表最佳效果。
3. 本次实际整数种子显示在主区及“生成参数”中，可**复制**或**复用为固定种子**。打开历史结果会显示该结果的种子；导出的PNG文字元数据和JSON都记录种子。外部导入且没有种子的素材明确显示未知。相同模型、提示词和参数下可尝试复现；种子本身不保证跨模型/版本一致。
4. 点击“生成完整动画”，完成后按源FPS**默认循环播放**，可暂停或取消循环。此时不抠图、不自动稀疏取帧；可另存完整MP4。
5. 点击“选帧与导出…”，在完整帧缩略图中勾选，或移动滑块后点“选取此帧”。当前帧号、源时间和已选数量均可见；默认不勾选任何帧，支持全选/清空、完整动画或所选帧循环预览。
6. 直接点**导出精灵图**保存PNG及可切片JSON，或点**导出所选PNG**在指定目录创建独立素材文件夹。仅处理勾选帧，按源顺序输出。可选透明背景、素材FPS和列数；不自动补帧/混帧/裁剪循环。同一窗口中，同组选帧切换导出格式可复用透明结果。过大的精灵图会要求减少选择或导出独立PNG，避免无界画布占用。

“导入动画…”也先预览完整本地MP4/MKV/MOV/WebM/AVI/GIF，再选择是否拆帧。“生成记录与缓存…”分别列出图片、完整动画和动画帧；没有另存的内容属于缓存。正在处理的源文件受保护。

## 模型选择

| 用途 | 当前路线 | 原因与边界 |
| --- | --- | --- |
| 无参考单图 | Z-Image Turbo | 原生理解中文，不叠加SDXL风格适配器；反向内容为软性文字约束。 |
| 参考重绘 | Z-Image Turbo | 复用现有权重；VAE编码参考图作为起点，可调重绘幅度，不保证精确大幅改视角/身份保留。 |
| 参考编辑 / 快速单图 | FLUX.2 Klein 4B | 4步，独立参考潜变量可改变视角/姿势；中文细节执行仍需检查，不全面替换Z-Image。真实验证前不启用。 |
| 导入旧工作流 | SDXL兼容 | 标准LoRA节点在工作副本中旁路，原文件不改；不自动重装退役权重。 |
| 自由动作 | MiniMax H3 / FreeVideo VDN | 独立Python与依赖，已完成本机真实动画。缺少已验证环境则明确不可用，不自动回退Wan。 |
| 历史骨骼 / Wan | 已退役 | 原成品仍可预览/导出；仅删除软件管理且收据、大小、发布SHA一致的Wan权重。 |

没有一个模型能保证所有画风、复杂接触、手脚细节和循环都准确。H3的本地VDN蒸馏/量化方案与官网托管完整处理流程不同；需要看同参考真实输出，不能单凭宣传替换全部模型。当前单图选型见[本机对照](MODEL_SELECTION.md)。源码、模型许可及评测说明分别见 [FreeVideo](https://github.com/FlashML-org/FreeVideo)、[MiniMax H3](https://github.com/MiniMax-AI/MiniMax-H3)、[Qwen编辑模型](https://huggingface.co/Qwen/Qwen-Image-Edit-2511)。

本机Qwen参考编辑在原加载、同步卸载、同步+原生分配/无页锁三组检查均未稳定完成，分别停在1/40、5/40、0/40步。只取消自己的诊断任务，记录保留，恢复原有Comfy启动参数，不混装Torch。栈观察到量化权重传输，尚不能断定唯一根因；官方仓库也有[Qwen/CUDA13兼容报告](https://github.com/Comfy-Org/ComfyUI/issues/15074)，不是下载更多风格模型即可解决。当前不开启该候选默认路线。

## H3独立安装与接续

本机已经单独安装，其他用户默认不下载这套约52.7GB的模型。普通桌面依赖不包含Torch。复现时使用FreeVideo固定提交 `518b9843c99ae57c8391706406260130f45eaa5c`，按其bootstrap帮助选择独立root、model目录与int8格式；先阅读[H3原始许可](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)，不能把开源理解成没有商用/地区条件。

```powershell
# 在独立FreeVideo源码目录，使用已有可运行的Python启动安装器；不要在Comfy环境中pip升级。
python -m freevideo_engine.bootstrap --root D:\AIPicturesH3 --models D:\ComfyModels\H3 --prepared-format int8 --network official --no-launch --storage compact --yes --accept-model-license --plain
```

`machine.json`的ready只表示安装及小算子探测通过。先运行一次受控真实测试，不会自动开放界面选项；实际查看动作和配色后再注册：

```powershell
python -m tools.probe_h3 --root D:\AIPicturesH3 --output data\videos\h3_probe --reference reference.png --action "角色原地自然行走，双腿交替迈步，双臂反向摆动" --seconds 4
python -m tools.register_h3 --root D:\AIPicturesH3 --result data\videos\实际完成目录\video.json
```

后台任务保存命令、独立进程号、日志、模型实际尺寸/帧数和来源哈希；取消仅结束自己的子进程树，不重启共享Comfy。H3源帧为24FPS，时长按原生17n+5帧网格向上对齐，实际时长会略长于输入值；完整预览和素材记录显示实际帧数。历史Wan视频仍按其记录的源FPS播放。没有固定时间超时后自动重算，也不自动重复付费调用。

## 转帧与质量边界

- 先RGB后Alpha，绝不为参考图提前抠掉白衣/白鞋再交给生成模型。已有Alpha只用于合成中性背景，不做重新分割。
- H3优先读取原生`rgb.npy`，保存逐像素PNG和RGB无损动画主文件，不从有损交付MP4再次取色；原生数据和原始视频都保留。缺少原生数据时明确记录视频压缩误差警告。
- 精灵图切片与PNG逐像素相同。无FXAA/TAA/DLSS、时间混合或历史帧融合。像素素材仍可另走`sprite_pipeline`，普通插画不强制调色板量化。
- 手动选帧的循环只是末尾回到首帧，不自动裁剪或合成接缝；跳跃/攻击也可取消预览循环。历史批量CLI仍有近闭环评分，不能保证无缝。
- 稀疏关键帧的节奏可能不同于原片段；严格保留原动作时序使用“全部源帧”或均匀采样。低帧率素材不能凭提取算法凭空变成高帧率动作。
- 当前完整预览按源平均帧率播放；导入可变帧率视频或不等间隔GIF时，节奏会按平均值近似。本机模型输出固定FPS，不受此限制。
- 后处理可保持已有颜色，不能恢复模型从未画对的手、衣服或被遮挡细节。不能承诺接近100%生成准确率。

原有自动取关键帧/均匀取帧仅保留为独立批量CLI；常规界面使用手动选帧：

```powershell
python -m tools.import_animation_video animation.mp4 --output out\sprites --frames 16 --sampling keyframes --loop --transparent
python -m tools.import_animation_video animation.mp4 --output out\all --frames 0
python -m pytest -q
```

新检查覆盖完整RGB视频无损编码/所有帧预览、显式拆帧、源FPS、精灵图回读、工作副本LoRA旁路、管理文件删除范围、独立引擎命令、真实Qt队列/预览/保存与取消。协议/图结构检查不等于真实模型画质验收，实机结果另记录。

## 本机实测

- 原生中文Z-Image无LoRA生成单个红色游戏药水瓶，约104秒，清晰出图；原后端启动方式保留。
- H3安全画布行走：768×1024、107帧、24FPS、4.458秒片段，完整流程约795.9秒。头脚没有首轮的裁切，仍需检查个别手部细节。
- 真实Qt界面H3自定义挥手：未连接Comfy、不用骨骼/LoRA，56帧、24FPS、2.333秒；侧身转正面、抬手挥动、放下。生成461.87秒，完整预览、8张透明素材、精灵图回读与ZIP导出共670.57秒。RGB逐像素保留，白衣Alpha保留、角落透明。循环接缝仍有警告，不能据此宣称任意动作无缝。
- 自动检查286项加7项子检查通过；六种骨骼研究动作及平台动作Qt回归通过。

昂贵的完整界面验收不会在普通测试中自动运行。需要复现时选择**全新目录**，确认其他GPU任务结束：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m tools.verify_video_first --reference reference.png --output data\acceptance\new_h3_wave --seconds 2
```
