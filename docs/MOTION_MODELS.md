# 完整骨骼动作模型

当前默认使用本地 Wan2.2 Animate 14B 的参考图 + 姿态视频工作流。不是把姿态图片附在普通 I2V 旁边：全部条件帧实际连接到 `WanAnimateToVideo.pose_video`，使用原生节点解码和保存。

## 本轮新增

安装根目录：`D:\Local Comfy\ComfyUI\models`。文件均固定发布版本，下载完成核对字节数和 SHA-256；不覆盖内容不同的旧模型。

| 文件 | 字节数 | 用途 |
|---|---:|---|
| diffusion_models/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors | 18,401,760,586 | 常规完整动作生成 |
| loras/AIPictures/animation/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors | 738,005,744 | 快速行为诊断，加速权重；常规生成不加载 |

总计 **19,139,766,330 字节（约 19.14GB）**。不新增 Python 依赖，不下载 Pose ControlNet。旧 SDXL、旧 Wan I2V 高低噪声权重保留。

Animate SHA-256：`2936b31473a967e7a429a6646bba60e7862d0938e178b58b2a140f391dd5b8e6`。

Lightx2v SHA-256：`85c4a61c30e0497aa44b91d93a893b624708461a56fe5485183b28fa07e2dfb3`。

来源是 Kijai 发布的模型转换/权重仓库，并非本项目训练：

- [Animate 固定版本发布目录](https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/tree/033a4e487f60220b3d6e469599a6aebc46e13cee/Wan22Animate)
- [Lightx2v 固定版本发布目录](https://huggingface.co/Kijai/WanVideo_comfy/tree/8260d429d19fd7a72304cad059160b95d843913f/Lightx2v)
- [ComfyUI 官方 Animate 工作流说明](https://docs.comfy.org/tutorials/video/wan/wan2-2-animate)

安装命令会进行真实下载/校验：

```powershell
& .\.venv\Scripts\python.exe -m tools.prepare_pose_models --models 'D:\Local Comfy\ComfyUI\models'
```

完成后点“连接 / 刷新模型”。模型与下载临时文件不进入 Git。

## 复用与参数

复用现有 Wan UMT5 FP8 文本编码器、Wan2.1 VAE，以及 CLIP-ViT-H-14-laion2B-s32B-b79K 视觉编码器。本机这套组合已经完成真实推理。需要 ComfyUI 的 WanAnimateToVideo、ImageBatch、TrimVideoLatent 等节点；检测人体使用已有 DWPose 插件。其他电脑不能仅安装本表两项就假定依赖完整，界面会枚举实际节点和模型。

常规参数为 20 步、CFG 1、Euler/simple、shift 5；快速诊断使用加速权重、6 步、CFG 1、shift 8。快速检查用于发现不动、动作阶段不全、短腿布局等明显问题，不能代替常规成品质量检查。加速权重不列入用户风格 LoRA，不根据提示词选择。

本机 GPU 为 12GB，模型需卸载到系统内存；原生 480×640、17 帧的一次常规 GUI 测试约 641 秒，包含透明处理。高内存负载会更慢。最终 768×1024 是输出画布，不表示原生推理达到该分辨率。

## 骨骼与质量范围

五类动作的周期由本项目程序生成。人体布局根据当前参考识别，检测失败时估计双足轮廓；跟/趾控制先转为标准身体脚踝条件。四足、无足与特殊机械尚无专用布局。

参考图相似性、完整动作周期、足部形状和透明分割分别检查。反向提示词和骨骼不能保证任意图片接近 100% 成功；单一静态骨骼在本机两组真实对照中失败，已移除常规入口。实际结果和反例见 [验证记录](VALIDATION.md)。

逐帧编辑、完整本地预览、自然动作、已用时及颜色修正见 [动作与颜色说明](MOTION_REFINEMENT.md)。
