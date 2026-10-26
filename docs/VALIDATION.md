# 本机验证记录

日期：2026-10-26。

环境：Windows，RTX 4080 Laptop GPU，12282 MiB 显存，约 32GB 系统内存。软件独立 Python 3.13.14、PySide6 6.12.0。既有 ComfyUI 0.20.1 位于 `D:\Local Comfy\ComfyUI`，其独立 Python 3.13.12、Torch 2.10.0+cu130。服务监听 127.0.0.1:8188。

已发现基础模型 `sd_xl_base_1.0_0.9vae.safetensors`；外部路径另有 IP-Adapter 权重。未发现可测试 FLUX、LoRA、Pose ControlNet 权重。不以现有节点存在推断权重完整。

已通过：

- 4 项结构/兼容测试：LoRA 连接、尺寸验证、本地地址限制、空成功响应解析。
- 真实桌面调用：768×768 SDXL、20 步，收到 20 次 progress 事件，界面计时器持续响应，PNG 下载、QPixmap 最终预览、任务参数和工作流保存成功。机器证据在 `data/acceptance.json`，截图在 `data/acceptance-desktop.png`。
- 真实按任务取消：在首个采样进度后按 prompt_id 取消，无全局 interrupt。证据在 `data/cancellation-test.json`。
- 真实队列与失败恢复：先提交一个不存在的 checkpoint，再加入两张 256×256、2 步测试任务，最终状态依次为 failed、completed、completed。证据在 `data/queue-test.json`。
- Python 编译检查通过。

限制：未测试不存在的模型管线；LoRA、FLUX、自定义训练/视频工作流未进行真实生成验证。手动另存文件对话框与长期压力测试尚未自动验证。断线后不自动重提交；任务可能继续在 ComfyUI 执行，需通过保存的 prompt_id 核查。当前资源管理是服务端模型枚举与卸载，不含模型下载和删除。

首次 ComfyUI 启动日志写在原聊天工作目录 `C:\Users\qcy_2\Documents\ChatGPT\生图软件`；后续通过项目 start-comfy 启动时日志位于本项目 data/logs。早期环境探测曾在原聊天目录创建临时 .venv；正式软件与独立环境均在桌面 AIPictures，AIGAMING 没有修改。
