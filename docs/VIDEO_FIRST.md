# 完整动画 → 游戏素材帧

当前主流程是 **提示词 / 可选参考图 → 自由动作 → 完整动画预览 → 用户选择拆帧**。骨骼动作保留为可选研究工具，不要求逐帧拖关节。LoRA 功能已停用；画风、主体和修改由描述及参考图决定。

## 软件操作

1. 运行 `run.bat`，选择“动画制作”。选择动作作为起始描述，或选择“自定义动作”直接写动作过程。动作说明可以修改，最终以文本框内容为准，不会因为提示词没有“动画”二字而转成单图。
2. 在“角色与生成…”选择参考图或仅文字、动画引擎及片段时长。无参考图时界面留空，不塞入默认人物。正向框写外观、场景和希望修改的部分，反向框写应避免的问题。
3. 点击“生成完整动画”，完成后以源帧率播放整个片段。此时没有抠图、量化或只保留8帧，也没有生成精灵图。可另存完整MP4。
4. 满意后点击“处理为动画帧…”，选择8帧、16帧或全部源帧（上限240张）。全部帧保留源FPS；稀疏帧可按关键姿态或均匀采样，并设置素材播放FPS。
5. 需要透明背景时在拆帧时勾选。先完整生成RGB，再分割Alpha，保留RGB。可播放、查看全部帧/精灵图，再“导出动画…”保存PNG、精灵图、GIF或ZIP。

“导入动画…”也先预览完整本地MP4/MKV/MOV/WebM/AVI/GIF，再选择是否拆帧。“生成记录与缓存…”分别列出图片、完整动画和动画帧；没有另存的内容属于缓存。正在处理的源文件受保护。

## 模型选择

| 用途 | 当前路线 | 原因与边界 |
| --- | --- | --- |
| 无参考单图 | Z-Image Turbo | 原生理解中文，不叠加SDXL风格适配器；反向内容为软性文字约束。 |
| 中文参考编辑候选 | Qwen-Image-Edit-2511 | 复用已安装权重，与Qwen-Image-2.1不同；本机兼容测试仍停顿，未设为默认，验证前禁用。 |
| 导入旧工作流 | SDXL兼容 | 标准LoRA节点在工作副本中旁路，原工作流文件不改；特殊适配器需改用自动工作流。 |
| 自由动作 | Wan2.2 I2V | 复用已有双专家模型；参考输入为原色RGB，不输入固定骨骼。文字模式先生成基准图再制作完整片段。 |
| 可选自由动作 | MiniMax H3 / FreeVideo VDN | 独立Python与依赖，低显存分块流式推理；需要真实动画完成后才开放。不是将大型权重塞进现有Comfy环境。 |
| 可选姿态研究 | 既有完整骨骼 / Wan Animate | 保留旧动作与编辑能力，用于姿态条件试验，不是正常自定义动作的必经步骤。 |

没有一个模型能保证所有画风、复杂接触、手脚细节和循环都准确。H3的本地VDN蒸馏/量化方案与官网托管完整处理流程不同；需要看同参考真实输出，不能单凭宣传替换全部模型。源码、模型许可及评测说明分别见 [FreeVideo](https://github.com/FlashML-org/FreeVideo)、[MiniMax H3](https://github.com/MiniMax-AI/MiniMax-H3)、[Qwen编辑模型](https://huggingface.co/Qwen/Qwen-Image-Edit-2511)。

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

后台任务保存命令、独立进程号、日志、模型实际尺寸/帧数和来源哈希；取消仅结束自己的子进程树，不重启共享Comfy。H3源帧为24FPS，时长按原生17n+5帧网格向上对齐，实际时长会略长于输入值；完整预览和素材记录显示实际帧数。Wan保留原生16FPS。没有固定时间超时后自动重算，也不自动重复付费调用。

## 转帧与质量边界

- 先RGB后Alpha，绝不为参考图提前抠掉白衣/白鞋再交给生成模型。已有Alpha只用于合成中性背景，不做重新分割。
- H3优先读取原生`rgb.npy`，保存逐像素PNG和RGB无损动画主文件，不从有损交付MP4再次取色；原生数据和原始视频都保留。缺少原生数据时明确记录视频压缩误差警告。
- 精灵图切片与PNG逐像素相同。无FXAA/TAA/DLSS、时间混合或历史帧融合。像素素材仍可另走`sprite_pipeline`，普通插画不强制调色板量化。
- 循环选项从真实源帧寻找近闭环区间，不复制首帧掩盖接缝、不合成不存在的姿态。跳跃/攻击可关闭循环；全部帧模式不裁剪，只控制播放是否循环。
- 稀疏关键帧的节奏可能不同于原片段；严格保留原动作时序使用“全部源帧”或均匀采样。低帧率素材不能凭提取算法凭空变成高帧率动作。
- 当前完整预览按源平均帧率播放；导入可变帧率视频或不等间隔GIF时，节奏会按平均值近似。本机模型输出固定FPS，不受此限制。
- 后处理可保持已有颜色，不能恢复模型从未画对的手、衣服或被遮挡细节。不能承诺接近100%生成准确率。

独立命令行转帧：

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
