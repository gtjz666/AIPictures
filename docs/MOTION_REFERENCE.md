# 动作参考：视频、GIF和PNG序列

动画模式下，在提示词下方选择：

- **＋角色 / 风格图**：主体身份、衣着、配色和画风；不选择时由文字指定外观。
- **＋参考动画**：导入MP4、GIF、MOV、WebM等动作片段。
- **＋动作帧**：多选2–1500张PNG，按文件名中的数字自然排序，再填写素材FPS。例如frame_1、frame_2、frame_10。

视频/GIF和PNG序列二选一，后导入的动作素材替换界面中的前一组。动作预览显示前4秒；不会替换角色图片预览。没有动作素材时继续现有文字/静态图片H3路线。选中动作素材后，不再自动插入走路等模板，以免和参考动作冲突。

正向框补充需要保留或修改的要求，例如：

> 黄色角色完成动作参考中的出拳和收拳；保持绿色眼睛、米白肚皮和深色手脚，不引入参考动画中的人物服装，固定镜头，全身可见。

动作起点可选。短GIF默认勾选“循环参考动作”，可自行取消；循环会重放原动作，不生成插值帧。模型输出按24FPS、17n+5帧网格对齐，界面显示实际预计时长，可能略长于填写值。取消循环后较短素材尾部保持末帧，模型仍可能延展动作。播放循环不等于保证首尾无缝。

导入原文件只读，复制到本地素材缓存；入队时再冻结为本次任务的独立副本。准备过程中可取消，修改下一次提示词/清空参考不会更改已经入队的内容。完成后沿用完整动画预览、自主选帧、透明PNG/精灵图导出。

## 实际线路

PNG序列直接读取图片；视频/GIF先按时间戳解码。GIF每帧独立延时与disposal由Pillow读取。统一成24FPS时只保持最近已展示的源帧，不做时间混合、光流或插帧。已有透明区域合成中性RGB，不提前分割主体。动作参考限制最长边512，不放大、不裁剪；角色参考独立输入。原始素材保留。

新线路使用**专用MiniMax H3 Ref2VA权重**及官方`MiniMaxH3ReferenceToVideo`，图片和动作视频分别进入独立参考槽。自有轻量节点将PNG批次送入官方节点，无需先把PNG压成视频再解码。官方节点用24FPS帧编码动作，另取2FPS画面提供语义理解。参考编码本身仍然需要计算，导入PNG不等于立即生成。

基础采样为20步res_multistep/simple，无风格或加速LoRA。正向词原文保留在官方参考提示格式内，以`<Picture 1>`负责主体外观、`<Video 1>`负责动作。反向词作为自然语言要求附加，不能保证全部避免。角色拓扑差异很大的参考可能只能迁移动作意图，不能保证逐帧精确模仿。

专用Comfy源码和依赖置于新的独立环境，原ComfyUI与普通H3环境不升级、不改原工作流。每次生成启动私有后端，结束后释放；取消/关闭通过私有进程Job结束本次计算，不依赖CUDA节点先响应中断。共享后端有其他任务时不开始本次GPU生成。日志、实际工作流和任务标识保存在本次动画缓存目录。

Windows加载已改用逐张量读取，并拆为两个私有进程：参考编码完成、原字节保存后彻底退出，再加载动画主模型采样。这样消除整文件映射的额外提交，并避免Qwen与主模型同时驻留。分阶段文件和SHA留在`native_encode`/`native_sample`，采样参数不变。[1455问题与查证](WINDOWS_MODEL_LOADING.md)。

## 可选环境与安装

桌面依赖不新增Torch。已有通过验证的H3 Python3.12/CUDA13环境可按下面方式创建私有环境，只读复用其运行库，不在原环境中pip升级：

```powershell
python -m tools.setup_motion_native --root D:\AIPicturesH3\reference-native --h3-root D:\AIPicturesH3 --models D:\ComfyModels\H3-reference
python -m tools.prepare_motion_models --models D:\ComfyModels\H3-reference --receipt data\motion-native-installation.json
```

安装器对已有目录明确停止，不覆盖安装。模型固定发布版本并校验SHA；可续传，既有完整文件SHA不同则保护保留。默认仅下载Ref2VA int8和视频VAE，共23,781,444,800字节；复用既有Qwen3-VL编码器，不下载另一份。音频VAE不是无声动作参考所必需，不默认下载。

固定源码Comfy-Org/ComfyUI `bb878b9ee35274e67931634ba9e8c338f8c06035`，额外依赖见`requirements-motion-native.txt`。安装器生成独立目录内的`machine.json`（validated=false），运行单次真实验收，目视检查并写`visual-review.json`的passed及偏差后，才能注册：

```powershell
python -m tools.probe_motion_native --folder data\videos\new_reference_probe --config D:\AIPicturesH3\reference-native\machine.json --motion motion.gif --image character.png
python -m tools.register_motion_native --config D:\AIPicturesH3\reference-native\machine.json --result data\videos\new_reference_probe\video.json
```

安装完成不等于生成或画质验收通过。没有验证配置时仍可导入、预览动作素材，但生成明确禁用，不暗中切到之前有重影的快速权重线路。

## 检查和参考来源

```powershell
python -m pytest -q tests/test_motion_reference.py tests/test_motion_native.py
$env:QT_QPA_PLATFORM='offscreen'
python -m tests.live_motion_reference
```

检查覆盖GIF时序、PNG自然排序/FPS、直接PNG通路、短片段循环、文件冻结、篡改/越界拒绝、实际按钮入队、图像/动作分离、任务取消与退出。真实模型视觉验收单独记录，不能用这些合成检查替代。

最终全量342项及7项子检查通过；真实Qt手选第4/21/44帧导出透明精灵图，再导出两张PNG，源RGB、切片及实际种子检查通过。透明处理约300.82秒，CPU抠图没有改动原始动画或再次生成。

- [Comfy官方H3原生工作流](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)：Ref2VA专用模型和参考节点、20–25步基础路线。
- [官方参考提示词格式](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md)。
- [Comfy模型及量化说明](https://huggingface.co/Comfy-Org/MiniMax-H3)。
- [Diffusers H3管线](https://huggingface.co/docs/diffusers/main/en/api/pipelines/minimax_h3)：参考生成与首帧生成使用不同权重。

本机实际质量、耗时、额外下载及未完成项目见交接记录。当前没有精灵图切片作为动作输入的按钮；PNG序列可直接使用。完整视频的“导入动画…”是预览已有成品，与这里的“参考动画”生成新动作是两项功能。

## 本次实测

用户提供的0.87秒、26帧出拳GIF＋透明黄色角色图片，经独立Ref2VA生成56帧/24FPS/512×768，完整流程487.1秒（后端计算349.09秒）。已查看10个关键画面：黄色身体、绿色眼睛、米白肚皮和深色手脚保留，主体执行出拳/收拳，无此前严重双影或复制人体服装。模型把动作重新演绎成了交替出拳，未精确复制原GIF的近大远小和节奏，身体比例/手形也会变化；不能称作精准逐帧重定向或百分之百保真。较早快速权重的重影样本被拒绝，正常入口不会使用它。

本次为新路线额外下载Ref2VA和视频VAE约23.78GB；研究安装阶段还下载了约605MB音频VAE，但无声动画路线没有加载它，后续安装默认跳过。另建独立Comfy源码/小依赖环境，原编码器和Torch只读复用。原Comfy和H3生成环境不改。
