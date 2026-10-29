# 参考配色与通用编辑研究记录（2026-10-29）

结论：**不把纯区域填色作为任意参考图的默认方案**。它适合闭合线稿，无法通用地恢复彩色插画、渐变卡通、遮挡及不同视角中的语义区域。像素素材另用明确的少色捕捉/色板约束；这也不能替代语义理解。

## DACoN 填色实测

来源：[作者代码](https://github.com/kzmngt/DACoN)、[论文](https://arxiv.org/html/2509.14685v1)。参考闭合线稿对照来自 [BasicPBC](https://github.com/ykdai/BasicPBC)，仅研究使用，其数据/代码许可不作为本项目商用授权。第三方研究仓库和权重在 `D:/ComfyResearch`、`D:/ComfyModels/reference-color`，没有复制进产品包。

执行两类对照：

- 原作者原生推理：干净闭合线稿的自身重填前景 RGB 完全匹配约 **99.626%**。这是单个正对照，不是跨帧、跨角色准确率。
- 12 个彩色参考/目标对照：红衣动漫、紫发白衣人物、黄色渐变卡通、写实人物参考图板；含自身重填、确定性形变及真实生成帧。对彩色输入提线后执行 DACoN 与参考区域主色填色；并非作者原始线稿数据管线。更强闭合阈值下，自身重填前景 ΔEab>10 的像素比例仍约 **43.47% / 32.40% / 26.32% / 57.06%**。真实生成目标没有完整真值，不能计算成品准确率。

目视发现腿部串成衣服红色、手臂变黑、奶油色腹部及眼睛区域丢失、渐变扁平化。Alpha 不变不等于配色正确，因此没有把此填色方案默认接入软件。复验工具：`tools/research_reference_fill.py`、`tools/research_fill_control.py`，本机对照位于 `data/reference-fill-research/`。

## 中文指令图像编辑备选

使用 [Qwen-Image-Edit-2511 官方模型](https://huggingface.co/Qwen/Qwen-Image-Edit-2511)与 [ComfyUI 官方模板](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_edit_2511.json)进行原生 40 步、CFG 4 测试，未用加速 LoRA。

两张真实生成结果：紫发侧视角色成功改正面全身；黄色卡通动物成功改三分之四视角迈步，保留主要黄色/奶油色与渐变。人物衣饰仍出现新的中央纽扣等细节，不能宣称完全保真。两次本机耗时约 **1060 秒 / 550 秒**，没有设置速度淘汰上限。

这两个测试支持继续研究指令编辑路线，**尚未作为桌面默认模型或动画路线接入**，也没有跨角色时间一致性保证。工具：`tools/research_general_generation.py --kind qwen`。产品当前通用单图仍用 SDXL/IP-Adapter；中文词表未知内容会保留，但并非完整中文理解。

## 本轮新增文件

- DACoN / DINOv2 / 提线研究权重：**1,575,684,303 字节**。
- Qwen 编辑、文本编码器、VAE：**30,172,239,743 字节**，位于已有 ComfyUI models 子目录。安装工具 `tools/prepare_general_models.py` 固定版本并校验 SHA-256；无 ComfyUI 代码或环境升级。
- 蜡笔、等距两款 SDXL 风格 LoRA：**56,890,720 字节**；已接入手选风格栏，见 [LoRA 说明](LORA_MODELS.md)。

合计 **31,804,814,766 字节（约 31.80 GB）**。模型均留在本地，不提交 Git。安装记录在 `data/reference-fill-research/downloads.json`、`data/general-model-installation.json`、`data/style-model-installation.json`。新增精灵管线本身无需下载任何 AI 模型，仅新增 PyYAML 运行依赖和 pytest 测试依赖。
