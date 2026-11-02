# Z-Image参考图重绘

Z-Image Turbo现在既能文字生图，也能以图片作为重绘起点。复用已安装的扩散模型、编码器与VAE；本轮新增模型下载为0，不运行额外分析模型或自动翻译，也不依赖FLUX、SDXL、ControlNet或LoRA。

## 使用

1. 运行`run.bat`，选择“单张图片”。在“模型与画面…”选择“Z-Image Turbo · 中文生成 / 参考重绘”，后台预设为“自动选择”。
2. 点击“＋参考图”。立即显示所选图片，Z-Image保持选中，不会因导入参考图自动切换FLUX。也可以导入后主动选择Z-Image。
3. 正向提示词描述目标画面的最终样子；例如“紫色盘发角色，右侧视全身，穿纯天蓝色无袖衬衫、黑色短裤和长袜，保持参考图画风”。反向仍是CFG1下的软性文字约束。
4. 在“模型与画面…”调整“重绘幅度”。默认0.45，低值保留更多原貌；高值允许更大变化，也更容易改变衣服、脸和构图。1相当于完全重新生成，不能保证参考细节。
5. 生成、预览、点击放大和另存与普通单图一致。种子默认随机，实际值可复制/复用，参数记录本次真实值。
6. “移除”清除参考绑定及其预览。下一次恢复纯文字生图，不继续使用旧图；此时隐藏重绘幅度，实际denoise固定为1。

导入原Comfy工作流仍进入兼容路线；要使用Z-Image内置流程，切回“自动选择”。H3动画和手动选帧不受此改动影响，时长上限没有改变。

## 生成流程

原参考图副本→按方向信息读取→将已有Alpha合成中性RGB背景→等比适配所选画布并补边→上传Comfy→LoadImage→VAEEncode→与中文提示词一起采样→原生PNG→按用户选择处理输出透明度。

这是真正把参考像素编码进采样起点，不是只在界面显示图片或仅把图片描述拼进提示词。参考图文件不改写，既有透明只是输入合成依据，不提前运行分割；生成完成后才按用户选择去背景。输入适配不拉伸人物，也不是对游戏素材帧做默认缩放。

提示词、种子、画布、参考文件与重绘幅度在入队时固定；之后改控件只影响下一次生成。可选API文字整理流程也会上传并绑定本次图片，不保留占位文件名。它不会因接入参考图而自动启用额外付费调用。

## 真实本机验收（2026-11-02）

复用原紫发侧视图，在实际Comfy Desktop端口串行完成，没有重启共享后端。以下都是新AI生成，未使用模拟结果：

| 测试 | 幅度 | 完成时间 | 目视结果 |
|---|---:|---:|---|
| 保持外观的小幅重绘 | 0.35 | 69.43秒 | 主要发色、白衣/黑短裤/长袜、侧身构图保留；发丝、手和鞋仍有变化 |
| 侧视转正面 | 0.85 | 58.32秒 | 转到三分之四视角，没有完整执行正面；脸、鞋和线条风格改变 |
| 实际Qt导入→描述换蓝上衣→点击生成→预览→另存 | 0.65 | 72.00秒 | 流程通过，seed20261103、原图SHA未变、另存逐像素一致；上衣仍接近白色，换色未充分执行 |
| 直接描述“整件纯天蓝色上衣” | 0.85 | 54.13秒 | 上衣成功变蓝，但衣摆、领结、鞋型和角色细节也改变 |

因此可以交付“Z-Image参考图重绘”，不能宣称已全面替代专门参考编辑模型，或已经解决所有角色一致性、精确换视角问题。“审阅参考图”在当前功能中表示用原图参与生成，不是新增一个视觉聊天模型逐项识别衣物。小幅度和高幅度的取舍仍需用户检查。

样本在本机`data/jobs/20261102_zimage_reference_*`，实际Qt记录在`data/acceptance/zimage_reference_qt_20261102`。源参考、准备RGB、实际工作流、提交标识、种子、耗时和输出哈希均保留。不要重复运行已成功样本。

## 检查与复现

```powershell
python -m pytest -q
$env:QT_QPA_PLATFORM='offscreen'
python -m tests.live_zimage_reference
# 以下会实际生成图片：使用新的目录，不能覆盖旧任务
python -m tools.probe_zimage_reference --url http://127.0.0.1:8189 --reference YOUR_REFERENCE.png --case retouch --denoise 0.35 --output data/jobs/NEW_REFERENCE_TEST
python -m tools.verify_flux_ui --family zimage --url http://127.0.0.1:8189 --reference YOUR_REFERENCE.png --denoise 0.65 --output data/acceptance/NEW_QT_TEST
```

检查覆盖参考潜变量连线、真实上传绑定、种子/幅度快照、透明合成与等比补边、缺节点明确失败、无参考不残留图片、SDXL隐藏参数不夹住Z-Image，以及实际Qt选择/清除/队列。结构检查不代替目视质量。

依据：[Diffusers官方Z-Image图生图与局部重绘说明](https://huggingface.co/docs/diffusers/api/pipelines/z_image)、[原始ZImageImg2ImgPipeline](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/z_image/pipeline_z_image_img2img.py)。本轮只交付整图重绘，未接入遮罩编辑界面，不将已存在的上游接口宣称为本软件已完成功能。
