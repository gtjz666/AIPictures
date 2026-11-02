# 当前生图选型与旧动画退役（2026-11-02）

先比较实际图像工作流，不因为名称更大或更新就添加一个分析模型。这里区分模型卡能力、软件实现和本机实测；有限样本不能证明任意提示词准确率。

## 候选与适用范围

| 路线 | 能力与成本 | 决定依据 |
|---|---|---|
| 既有 Z-Image Turbo | 原生中英文无参考图创作；6B、9步、CFG 1 | 保留为已验证的文字生图路线。现有实现不支持语义参考编辑，不能靠提高图生图保真度来实现侧视转正面 |
| FLUX.2 Klein 4B distilled | 同一模型支持文生图、参考编辑；4步、CFG 1；Apache 2.0 | 在既有 ComfyUI 内对照测试，不覆盖原工作流。复用已安装 Qwen3 4B FP8 mixed 编码器，按 FLUX2 编码方式提取对应层；新增扩散模型与 VAE 共8,087,317,004字节 |
| SDXL / Juggernaut v9 | 兼容原用户工作流、采样与小幅重绘参数 | 作为兼容入口保留，不删除原模型，不把低重绘幅度误称为可自由换视角 |
| 既有 Qwen-Image-Edit 2511 | 已有权重，但原后端多次加载/采样停顿 | 未通过本机验收，不作为默认，也不因文件存在就开放按钮 |
| Qwen-Image 2.1 | 7B视觉组件，另需编码器；文生图、编辑、原生RGBA；官方示例40步 | 当前采用Qwen Research License，商业使用需另行许可；本机当前后端缺少该路线原生支持。因此不作为游戏素材工具的默认替换，也未下载 |
| Qwen3.8-27B | 图片/视频/文本输入，文本输出 | 是理解模型，不能直接生图；不新增27B分析权重。先让图像模型直接理解提示词和参考图，已有用户自选API整理保持可选、默认关闭 |

FLUX.3 Image Klein也列入资料检索；当前后端未包含其新架构，公开权重下载另有访问要求。本轮不盲目升级共享Comfy环境或把未经本机测试的发布数字当作速度依据。

## 本机结果与选择

RTX 4080 Laptop 12GB、既有ComfyUI 0.20.1，同画布同种子；共完成11张真实AI输出：两条路线各四类、额外英文对照、正面参考编辑和实际Qt编辑。

| 相同中文任务 | Z-Image后端执行 | FLUX后端执行 | 已查看的差异 |
|---|---:|---:|---|
| 动漫全身 | 261.07秒 | 97.95秒 | Z保留盘发、无袖；FLUX中文案例变成短发、短袖，不能因为更快就替换默认 |
| 写实肖像 | 154.47秒 | 82.71秒 | 两组均有清晰正面五官；FLUX画面更平滑，Z有更多皮肤纹理，风格偏好不同 |
| 游戏药瓶 | 130.63秒 | 89.05秒 | 两组均单个红色玻璃瓶；FLUX补全指定金属环，Z该环有遗漏 |
| 水彩村庄 | 137.49秒 | 87.21秒 | 两组均完成左木屋、中桥、右大树布局；严格正交横版视角仍不保证 |

以上为后端记录的execution_start→execution_success，避免把一次肖像监控文件锁后的恢复等待算成模型推理。常规端到端：Z四组约160–265秒；FLUX三组约102–114秒，肖像恢复了原任务结果，未伪造端到端时长。首组Z与下载并行，缓存/系统负载也不同，不能把这轮数字当成普适跑分。

- **文字默认保留Z-Image**，原因是中文角色细节执行更完整，而非盲目追求最少步数。FLUX保留为用户主动选择的快速生图和参考编辑。
- **参考编辑采用已验证FLUX**：用户原紫发侧视图→正面全身，约90.11秒，主要服装/配色与绿眼睛保留；细小形状仍有变化。
- **真实Qt完整链路**：导入同一张原图→正面＋上衣换蓝色→预览→另存，116.20秒完成，实际seed=20261103；另存与预览逐像素一致，原始参考SHA未变，无分析/翻译/云端调用。上衣和视角执行正确，但长袜新增条带且高度变化、领结形状变化；仍不能承诺完全保真。
- **英文对照**：FLUX同义英文样本恢复盘发/无袖，约102.76秒；一个对照不足以证明自动翻译普遍更准。没有据此强制启用旧小译器或下载27B分析模型；中文用户仍默认Z-Image。
- 全量检查覆盖独立参考条件、无参考不放图片、参数/种子、模型验证门槛、H3无旧路线回退、选帧导出、文件锁重试及限定范围删除。原生Windows界面也已检查；无屏幕测试环境的中文字体截图不能当成实际桌面的字体缺陷。

**新增约8.09GB，删除4个SHA一致的管理Wan权重共53,727,153,147字节，净减少约45.64GB。** 旧Wan VAE的大小相同但SHA不同，按保护规则保留，未强删。原用户模型与工作流保留。本轮未重新跑H3视频，沿用已验收引擎并检查新入口/历史预览，未向聊天发送GIF。

本机结果：`data/acceptance/image_models_20261102/`、`image_reference_20261102/`、`flux_qt_20261102/`；管理删除收据`data/wan-retirement.json`。不要为检查重复运行已成功样本。

## 工作流实现

- FLUX：原始参考图先合成普通RGB供模型读取，作为独立参考潜变量条件；输出从新潜变量采样。因此文字可以改变姿势、视角和场景，而不强制复制输入姿态。没有参考图则完全没有LoadImage/参考条件节点。
- 保留用户中文原文，直接进入图像编码器，不先调用另一个LLM。不把H3内部必需的文本编码器视作额外分析服务。
- FLUX与Z-Image的CFG 1蒸馏路线没有独立反向引导通道；界面反向词被记录并作为自然语言排除要求，属于软约束，不能承诺消除所有错误。
- 原始RGB生成完后才按用户选择去背景。导出动画帧只处理勾选源帧；不混帧、不强制缩放、不添加全局抗锯齿。
- 新模型仅在组件齐全且本机真实验收记录validated为true时启用；没有H3时明确不可用，不回退到已停用模型。
- 自动路线的固定采样设置不再占用可编辑参数行；只显示实际有效控件，随机/固定种子逻辑不变。

## 动画退役范围

主界面只提供MiniMax H3。移除骨骼研究入口、旧角色基准应用入口，以及Wan动画提交代码；已有历史视频和帧仍可预览/导出。旧骨骼算法文件留作历史数据读取/研究，不再是正常生成路径。Wan/骨骼安装器拒绝重新安装。

`tools.remove_managed_wan`只处理五个安装收据、大小、发布方SHA均匹配的管理权重，逐文件核验绝对路径和共享后端空闲状态；文件改变、路径重定向或后端有任务则保留/停止。原用户的SDXL、ControlNet、姿态检测、IP-Adapter、CLIP Vision及工作流均不在删除清单。删除收据保存在本机data，不上传用户路径。

## 测试方式

四组固定中文提示词覆盖动漫、写实、道具、场景。相同尺寸、seed=20261102、串行冷加载；每个目录保存原图、完整工作流、提交标识、参数、耗时与文件哈希。参考编辑额外检查由侧面改正面、原配色/服装和细节保留情况。计时包含模型加载与解码；系统负载、磁盘缓存和共享后端会影响时间，不是GPU宣传跑分。

```powershell
python -m tools.compare_image_models --family zimage --case anime --case portrait --case prop --case scene --output data/acceptance/image_models_NEW
python -m tools.compare_image_models --family flux_klein --case anime --case portrait --case prop --case scene --output data/acceptance/image_models_NEW
python -m tools.compare_image_models --family flux_klein --case front_edit --reference YOUR_REFERENCE.png --output data/acceptance/image_models_NEW
python -m pytest -q
```

已有任务目录一律拒绝覆盖/重提；检查旧提交记录后再选择新目录。新安装：`python -m tools.prepare_flux_klein --comfy-root "YOUR_COMFY_ROOT"`，可加`--proxy`；需要已有、SHA相符的共享编码器。下载不等于验证，不自动开启界面。查看真实结果后执行`python -m tools.register_flux_klein --text-result TEXT_RESULT.json --reference-result REFERENCE_RESULT.json`。登记器核对两类成功历史、实际模型、图像和哈希后才写本机`data/flux-klein-settings.json`；拒绝用纯文字结果替代参考验收。

## 原始资料

- [Z-Image官方项目](https://github.com/Tongyi-MAI/Z-Image)、[ComfyUI原生工作流](https://docs.comfy.org/tutorials/image/z-image/z-image-turbo)
- [FLUX.2 Klein 4B模型卡与许可](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B)、[官方Comfy教程](https://docs.comfy.org/tutorials/flux/flux-2-klein)、[官方编辑模板](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_flux2_klein_image_edit_4b_distilled.json)
- [Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1)、[原始研究许可](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)
- [Qwen3.8-27B输出模态](https://help.aliyun.com/zh/model-studio/qwen3-8-27b)
- [FLUX.3官方Comfy教程](https://docs.comfy.org/tutorials/flux/flux-3-klein)
- [MiniMax H3原始许可](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)：沿用已验收引擎；适用地区、商业产品标识及营收门槛等限制依旧存在，不属于全球无限制商用许可。
