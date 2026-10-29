# 动画清晰度：生成与导出

## 实际问题与修正

旧动作流程在 480×640 生成，然后把图放大到 768×1024。细长人物的手、鞋、发丝只占较少的原生像素，放大不能恢复模型没有生成的线条。Wan VAE 的空间压缩为 8 倍，进一步限制小局部可用的生成空间。后者可在 [Wan 官方配置](https://github.com/Wan-Video/Wan2.2/blob/main/wan/configs/wan_animate_14B.py) 与 [推理实现](https://github.com/Wan-Video/Wan2.2/blob/main/wan/animate.py) 核对。

默认改成 **原生细节 · 768×1024**。参考构图与原始关节坐标保留，姿态条件按实际推理尺寸绘制，原始帧、原生透明帧及常规输出尺寸一致。导出不再对这个模式执行二次尺寸放大。**快速预览 · 480×640** 保留为显式选择，其任务记录明确标识 `post_enlargement=true`。

另一个实际问题是区域自动校色：本次原生结果的首帧有 35,679 / 97,511 个可见像素被后续配色/局部颜色修复改写，最大通道改动 170，皮肤和渐变出现细碎斑点。因此默认 **保留生成原色**：去背景只改 alpha，停止自动区域配色、曝光改写与发色/手部 RGB 修复。**参考配色校正** 变成可选操作，原始图始终保存。参考图仍参与模型条件，不需要靠后期改写所有颜色来维持外观。

没有引入锐化、生成式超分、FXAA、TAA、DLSS 或跨帧像素混合。像素素材导出的 snap / 调色板步骤仍只在用户主动导出像素素材时运行。

## 已查证的官方资料

- [ComfyUI 原生 Animate 指南](https://docs.comfy.org/tutorials/video/wan/wan2-2-animate)：核对模型、CLIP Vision、Wan2.1 VAE 及原生姿态控制方式；输出宽高需为 16 的倍数。
- [Wan Animate 官方推理](https://github.com/Wan-Video/Wan2.2/blob/main/wan/animate.py)：官方使用 DPM++ / UniPC 求解器；本软件提供 Euler / DPM++ 2M 对照。ComfyUI 调度与官方实现并非逐行相同，不能仅凭采样器名字宣称结果等价或更好。
- [官方 VAE 文件](https://huggingface.co/Comfy-Org/Wan-2.1/blob/main/split_files/vae/wan_2.1_vae.safetensors)：本机 SHA256 已核对为 `2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b`，与发布文件一致。未发现 VAE 文件损坏或误用的证据；这并不表示 VAE 编解码无损。
- [Wan-Animate-2 官方项目页](https://humanaigc.github.io/wan-animate-2/)：所查页面提供论文与演示，没有可直接接入的代码/权重下载入口，本次没有将其作为已可用的替换模型。

## 本机真实对照

2026-10-29，以同一角色、固定 seed `2776800848084959`、同一组关节坐标、提示词和 20 步进行对照。基准为旧的 480×640 原始生成结果；两种原生试验使用 768×1024。每组采样目标为 17 帧，导出 8 帧完整步态。

原生 Euler 组已完成 17 帧生成与 PNG / Sprite Sheet / GIF 导出。100% 同画布局部对照中，发丝、前臂和鞋底轮廓明显改善，白色缺块减少；仍存在细小色线、部分手指和服装结构变化，不能宣称任意人物都已完全准确。该组推理与下载约 602 秒；耗时随缓存、硬件和场景变化，不作为性能承诺。

DPM++ 2M 试验完成并保存了有限值的潜变量，随后原生 VAE 解码未正常结束。已在用户授权后重启同一个后端，按同一潜变量恢复完整 17 帧；未重新采样。结果与 Euler 接近，本图未观察到更换采样器带来的显著清晰度提升，因此默认继续使用 Euler。原始中断记录与恢复任务均保留。

软件现在把采样和解码拆成两个真实 ComfyUI 任务：先保存潜变量，再按后端空闲状态请求卸载大模型，上传原始潜变量交给同一 VAE 解码。两阶段不修改 seed、潜变量、模型精度或像素，不做插帧、时间混合和二次生成。实际工作流分别保存在 `video/workflow.json` 与 `video/decode/workflow.json`，高级工作流显示当前真实执行阶段；`sampling_result.json` 和解码记录分别保存两个任务标识。

使用生产解码函数进行了真实 API 验收：只输出潜变量的任务成功返回，完整 17 帧恢复解码与上一次原生解码的 RGB **逐像素一致**。8 张最终 PNG 尺寸一致，保留生成 RGB；精灵图逐帧切片回读与 PNG 完全一致，背景角点 alpha 为 0。163 项自动测试、7 个子测试及两项真实 Qt 检查通过。本次没有新增模型下载。

原生透明帧支持复用已验证的背景 alpha 重新导出。复用前必须与对应原始生成帧逐像素核对 RGB 和尺寸；左右朝向按原始生成方向还原后核对，拒绝给另一组帧套旧 mask。新旧输出使用不同目录，避免覆盖作品。

## 软件中使用

“角色与生成…”选择动画与角色来源，清晰度选 **原生细节 · 768×1024**，配色选 **保留生成原色**。默认 Euler、20 步。采样方式可手动对照，参数在任务创建时保存，不会因之后修改界面而改动正在执行的任务。

新任务的原始解码帧在 `video/decode/`，原生透明帧在 `frame_NNN/matte_native.png`；历史单任务动画的原始帧仍在 `video/`。`sequence.json` 记录 `spatial_detail`、`color_mode`、`color_processing`、`workflow_stages`、逐帧 `post_color_rgb_preserved` 及透明处理是否改 RGB。

## 重复测试

使用仓库虚拟环境 Python，在仓库根目录执行；两条采样命令建议依次执行，避免多组大模型任务排队占用同一缓存：

```powershell
python -m tools.compare_animation_detail --sequence "已有完整骨骼动画目录" --out data/detail-euler --width 768 --height 1024 --sampler euler
python -m tools.compare_animation_detail --sequence "已有完整骨骼动画目录" --out data/detail-dpm --width 768 --height 1024 --sampler dpmpp_2m
python -m tools.review_animation_detail --baseline "旧动画/video/result.json" --trial data/detail-euler --trial data/detail-dpm --out data/detail-comparison
python -m tools.reexport_animation_colors --sequence "已完成动画目录" --out "新的动画输出目录" --mode original
python -m pytest -q
python -m tests.live_animation_detail_controls
```

对照图由实际生成的原始 RGB 制作；只为比较旧流程的放大结果而执行其既有 Lanczos 尺寸转换。没有增强对照图的纹理或修改配色。图中像素数量和唯一帧数量均不能替代人物结构与一致性的人工验收。
