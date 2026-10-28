# LoRA 风格模型

使用顺序：**采样与 LoRA → 手动选择风格类型 → 手动选择具体 LoRA → 生成**。默认不使用 LoRA；提示词不参与模型或类型选择。类别与说明来自本项目的静态目录，不运行分类器或语言模型。

主动选择后，界面给出推荐强度，并将需要的触发词 / 风格短语写入本次提示词。模型只调整风格倾向，不锁定特定人物身份，也不保证数量、肢体、构图或动作全部准确。

全部模型基于 SDXL 1.0。单张生成和文字动画的前置角色图可用；SDXL 权重不会送入 Wan。当前已安装权重总计约 1.30GB。

| 类型 | 选择项 | 推荐强度 | 触发词 | 作者来源 / 原文许可 |
|---|---|---:|---|---|
| 动漫 | 日系动漫 | 2 | anime | [ntc-ai](https://huggingface.co/ntc-ai/SDXL-LoRA-slider.anime) · mit |
| 动漫 | 手绘动画 | 0.8 | Studio Ghibli / StdGBRedmAF | [artificialguybr](https://huggingface.co/artificialguybr/StudioGhibli.Redmond-V2) · author-page |
| 动漫 | 漫画线稿 | 0.8 | LineAniAF / lineart | [artificialguybr](https://huggingface.co/artificialguybr/LineAniRedmond-LinearMangaSDXL-V2) · creativeml-openrail-m |
| 卡通 | 可爱卡通 | 0.8 | CuteCartoonAF / Cute Cartoon | [artificialguybr](https://huggingface.co/artificialguybr/CuteCartoonRedmond-V2) · creativeml-openrail-m |
| 卡通 | 3D 角色 | 0.8 | 3D Render Style / 3DRenderAF | [artificialguybr](https://huggingface.co/artificialguybr/3DRedmond-V1) · author-page |
| 卡通 | 黏土动画 | 0.8 | Clay Animation / Clay | [artificialguybr](https://huggingface.co/artificialguybr/ClayAnimationRedmond) · creativeml-openrail-m |
| 写实 | 写实增强 | 1.5 | more realistic | [ostris](https://huggingface.co/ostris/photorealistic-slider-sdxl-lora) · other |
| 写实 | 人像摄影 | 0.8 | instagram model | [artificialguybr](https://huggingface.co/artificialguybr/selfiephotographyredmond-selfie-photography-lora-for-sdxl) · other |
| 插画 | 水彩绘画 | 0.8 | 无需 | [ostris](https://huggingface.co/ostris/watercolor_style_lora_sdxl) · apache-2.0 |
| 像素 | 游戏像素 | 1 | 无需 | [nerijs](https://huggingface.co/nerijs/pixel-art-xl) · creativeml-openrail-m |

写实增强选中后附加 photograph / photorealistic / natural lighting；水彩选中后附加 watercolor painting 等风格短语。它们由明确选择决定，不分析提示词来推荐 LoRA。各文件遵循作者页面所列条款；author-page 表示页面未单列统一许可，不将其解释为统一商用授权。

## 适用与设置

- 人物建议先用 768×1024、24–30 步、DPM++ 2M / Karras。正向写清数量、外观和构图。需要单人时可在反向加入：多个人物、重复人物、人物设定图、三视图、多视图、画面分格、拼贴、头部裁切、脚部裁切。
- 动漫线稿可用 colorful / black and white 调整彩色或黑白；像素模型会有意保留像素边缘，可在放大窗口关闭“平滑缩放”。
- 部分样例会生成多视图、裁切或不希望的道具，这属于生成质量限制；不能把加载成功当作每张成品质量通过。
- 参考图 Wan 动画与旧版骨骼流程禁用此选择。动画“仅文字描述”会启用选择，用于先生成的 SDXL 角色图，随后由 Wan 延续画风。
- 单基础模型模板中，所选 LoRA 接在 checkpoint 的 model / clip 输出，位于 IP-Adapter 上游，VAE 保持原连接。作者原有 LoRA 不覆盖；选择项会叠加，界面有提示。多基础模型需在高级编辑器配置。
- 未登记的本地 LoRA 标为“未分类”；不依据文件名或提示词猜测其风格。

有参考图并使用“优先保留细节”时，单图也暂停应用风格 LoRA 和高清重画；原手选项保留。要改变参考图风格，请在“模型与画面…”明确切换“允许按描述重绘”。

## 高清修复与文件位置

LoRA：`D:\Local Comfy\ComfyUI\models\loras\AIPictures`。另安装官方 [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) 的 RealESRGAN_x4plus_anime_6B（约 17.9MB）及 RealESRGAN_x2plus（约 67.1MB），位于同一 models 下的 upscale_models。两者在“模型与画面 → 画质优化”手动启用；默认标准平滑只处理预览与透明边缘，不运行超分。

新电脑重新安装：

```powershell
& .\.venv\Scripts\python.exe -m tools.prepare_style_models --models 'D:\Local Comfy\ComfyUI\models'
```

本次新增约 1.38GB。LoRA 固定下载版本并与 Hugging Face LFS SHA-256 核对；官方超分发布文件核对大小并记录 SHA-256。下载结果在 data/style-model-installation.json。权重和样图均留在本地，不提交 Git；安装后在软件点击“连接 / 刷新模型”。

## 本机验证

45 项单元测试与真实 Qt 检查覆盖：默认留空、旧参考不恢复、选图显示原图、移除清空、手动类型筛选、提示词不改变 LoRA、模板 model / clip 连接和取消所选层、平滑缩放开关。

10 款模型分别做同提示词 / 同种子的 0 强度与推荐强度对照，共 20 次实际 SDXL 推理，均产生可测的 RGB 变化；写实和水彩增加明确风格短语后又进行 4 次针对性对照。这些验证接入与风格影响，不等同于全部样图都达到成品标准。

真实桌面测试完成“无参考图 → 手选 LoRA → 手选动漫高清 → 采样进度 → 透明 PNG → 界面预览及保存”。两种高清修复均使用已生成的人物 / 卡通原始帧实际运行，验证输出顺序与 768×1024 尺寸；没有重新运行整段 Wan 动画。文字动画接入 LoRA 的图结构已验证，本轮未重复完整 Wan 视觉验收。

记录：data/style-models-acceptance.json、data/style-refinement-acceptance.json、data/style-controls-acceptance.json、data/style-image-acceptance.json、data/quality-models-acceptance.json。
