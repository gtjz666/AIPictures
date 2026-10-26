# AIPictures

Windows 独立本地 AI 图像创作桌面软件，第一阶段。Python + PySide6，ComfyUI API 推理。

代码仓库：https://github.com/gtjz666/AIPictures

仓库只保存源码、文档、测试和启动脚本。`.gitignore` 排除了本地环境、生成结果、数据集、模型权重、日志和凭据；克隆后需运行 `setup.bat` 并连接自己的 ComfyUI。`start-comfy.ps1` 中的安装路径应按电脑实际情况调整。

## 启动

1. 已在本机配置独立 `.venv`。首次迁移或重装运行 `setup.bat`（Python 3.13）。
2. 使用已有 ComfyUI Desktop，或者双击 `start-comfy.bat` 启动现有本地 ComfyUI。默认地址 `http://127.0.0.1:8188`。第一次启动较慢，日志在 `data/logs`；Desktop 若使用其他端口，在软件顶部更改连接地址。
3. 双击 `run.bat`。点击“连接 / 刷新模型”，选择已安装 checkpoint，输入提示词，点击“添加生成任务”。
4. 可连续添加任务；当前任务完成后执行下一项。预览下方可另存 PNG；原结果自动保存在 `data/jobs`，左侧双击历史记录预览。

内置 SDXL 文生图支持尺寸、种子、步数、CFG、采样器、调度器以及一个可选 LoRA。列表来自服务端真实模型发现，不代表任意 LoRA 与 checkpoint 相互兼容；需要匹配模型架构。当前未安装可测试 LoRA 或 FLUX 权重。自定义 API 工作流导入使用 JSON 原参数，右侧参数不会覆盖它；需 SaveImage 输出节点。UI 格式 JSON 会被拒绝。

原有 AIGAMING 与 ComfyUI 工作流未被覆盖；没有下载模型、没有安装自定义节点。仅新增标准 ComfyUI 生成输出和本软件数据。

## 测试与验收

在本目录 PowerShell 运行：

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
& .\.venv\Scripts\python.exe -m tests.live_smoke
```

后者需要运行中的 ComfyUI 和现有 SDXL 权重，会实际执行 768×768、20 步生成，打开真实 Qt 窗口，经窗口的入队逻辑提交，验证下载图片和 QPixmap 预览，保存 `data/acceptance.json` 与 `data/acceptance-desktop.png`。会消耗 GPU 时间并产生一张图片。

第一阶段验收：连接返回真实 checkpoint；任务进入 ComfyUI 队列；采样进度随事件变化；界面仍可操作；最终图片可预览且 PNG/参数/工作流落盘；重启可浏览结果。取消应只影响本软件当前任务；错误显示在日志并写入 job.json。

手动复查：重复添加两次任务观察串行完成；增加步数后取消当前任务；关闭 ComfyUI 后刷新观察连接错误；另存图片并打开；生成完成后释放显存。程序有后台操作时会阻止立即关闭，避免销毁工作线程，需先取消并等待。

阶段二验收目标：导入已授权数据集→预处理/标注→独立环境完成一轮真实 LoRA 训练→模型版本登记→在第一阶段生成测试图。

阶段三验收目标：编辑保存骨架→关键帧插值→姿态控制真实出图→检查角色一致性和抖动→逐帧修改→导出 PNG/Sprite Sheet/GIF/MP4。

阶段四验收目标：独立视频工作流真实生成→首尾帧与参数可复现→预览导出→验证 12GB 显存策略和取消/错误处理。

模块设计见 `docs/ARCHITECTURE.md`。GitHub 创建步骤见 `docs/GITHUB.md`。
