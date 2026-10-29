# 动画配色一致性与工作流对照

## 定位结果

2026-10-29 对照粉发红衣、紫发白衣的本机缓存：部分发色和曝光变化已经存在于模型输出的原始 RGB 中，并非透明棋盘或播放器叠加造成。旧流程以本段动画的中位颜色做小幅时间校正，整段共同偏离参考图时无法拉回原角色配色。

本次逐节点核对了 [Comfy 官方 Animate 文档](https://docs.comfy.org/tutorials/video/wan/wan2-2-animate)、[官方工作流](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_wan2_2_14B_animate.json) 与 [Wan 官方推理实现](https://github.com/Wan-Video/Wan2.2/blob/main/wan/animate.py)。复用现有 Wan Animate 14B FP8、UMT5、CLIP Vision H、Wan2.1 VAE；保留普通模型的 20 步、CFG 1、shift 5，不把蒸馏加速图的参数直接套到普通采样。

官方实现也在 VAE 解码前裁掉参考潜帧，本次没有颠倒这一顺序。现有短序列一次生成，没有采用多段反复解码/编码的长视频循环。[维护者关于长循环漂色的分析](https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/1277)是后续长视频的注意事项，不能据此断言当前短序列的根因。

[WanVideoWrapper 维护者说明](https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/1380)指出白色背景会干扰整图参考校色。ComfyUI 的 [ColorTransfer 实现](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_post_processing.py)提供 Lab/直方图等方式，但本机版本没有前景遮罩输入。因此这里在本地透明导出阶段只统计角色前景，不添加整图直方图节点。

## 原参考图配色校正

“优先保留细节”动画及纯文字生成后的角色基准图使用此流程：

1. 原始模型 RGB 保留，先生成透明前景。
2. 只从实心前景取样；按骨骼位置划分头部、上身、下身、脚部，并平滑混合区域边界。这是粗略区域，不是语义分割。
3. 从原参考图和当前帧提取少量颜色原型，以颜色距离和占比匹配，在 Lab 空间估计有限的平滑偏移。
4. 每帧都与同一原参考比较，不把修订后的上一帧作为下一帧的颜色基准。
5. 已匹配的颜色、深色轮廓受保护；下身/脚部允许参考图其他区域已有颜色，以保护抬起的白色鞋面。颜色原型只用于计算偏移，最终图片不做调色板量化。
6. 严重且不确定的颜色匹配跳过或限幅，并在逐帧视图显示“待复查”。原有紫/蓝发异常色、浅色鞋面与手部的小范围保护仍保留。

此阶段只修改 RGB，Alpha、画布和肢体位置不变。`reference-palette-plan.json`、每帧 `palette-quality.json` 和 `sequence.json` 记录方法、修改像素与不确定区域；已有原始图和修正前图保留。

颜色距离只是诊断指标，不是角色身份或成品准确率。粗区域无法可靠区分所有遮挡的发丝、衣物和手部；已经生成错误的花纹、配饰、鞋型、重影不能靠校色恢复。原图颜色一致不等于几何细节一致。

## 已完成缓存重处理

可以复用原始透明帧修订颜色，无需重新运行 14B：

```powershell
& .\.venv\Scripts\python.exe -m tools.review_animation_colors '原动画缓存文件夹'
```

工具在 `data/animations` 新建带 `palette` 的副本，导出 PNG、GIF、Sprite Sheet，并明确记录没有新推理。原缓存与用户保存文件不变。重启软件后可在生成记录打开“配色修订”条目。它不是重新生成动作，也不能证明推理阶段的角色细节已改善。

## 人脸条件实验

官方 Animate 工作流具有独立面部条件分支。本次测量原角色的可信面部关键点，裁切参考面部并重复到完整条件帧；这是固定原表情，不是表情动画。轮廓估计或面部关键点不足的非人类角色跳过。本机真实测试耗时明显偏高且尚未通过完整视觉验收，因此仅保留诊断入口，常规界面关闭此分支；不将节点接通等同于质量通过。当前默认推理图保持原完整姿态序列，配色改进在透明导出阶段生效。

诊断入口 `python -m tests.live_reference_consistency <原缓存>` 会在引擎队列空闲时提交上述对照，并记录功能执行和视觉检查。按用户要求，不采集内存、温度，也没有对应的自动取消阈值。历史测试中的监测与取消记录保留为历史事实。

本次只下载了官方工作流 JSON 用于核对，没有新增模型、依赖或修改 ComfyUI 源码；用户原工作流保留。
