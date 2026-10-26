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

## 在软件中编辑工作流

顶部切换到“工作流编辑”，即可使用嵌入式 ComfyUI 节点编辑器，无需打开外部浏览器。支持现有 ComfyUI 的节点添加/删除、参数编辑、画布缩放和节点连线；可用节点和权重取决于本机 ComfyUI。

1. 在图像页选好参数，切换“工作流编辑”，等待编辑器就绪，点击“载入图像页工作流”。也可用“打开工作流副本…”打开已有 **UI 或 API JSON**，与图像页仅导入 API 的入口不同。
2. 在画布内修改提示词、模型、尺寸、采样器等，拖动端口连接节点；在画布空白处双击可搜索节点。
3. 点击顶部紫色“运行到软件任务队列”。软件切回图像页，通过原有队列执行，显示进度、预览并保存图片。该链路当前面向有 `SaveImage` 输出的图像工作流。
4. 点击“保存工作流副本…”保存可再次打开的 UI JSON，保留节点位置和连线。执行时任务目录还会额外保存 `editor_workflow.json`，可在工作流页重新打开继续编辑。

编辑器使用 `data/browser` 下的独立浏览器缓存，不读取 ComfyUI Desktop 或外部浏览器的缓存。打开文件在内存中编辑，顶部保存按钮由你选择副本位置。内嵌 ComfyUI 自带的蓝色“运行”按钮仍属于 ComfyUI 自己的队列，其任务不会自动复制到本软件历史；需要统一进度、取消和自动保存时使用顶部紫色按钮。编辑器内 ComfyUI 的保存/设置功能操作的是同一台本地服务。

此功能依赖 PySide6 WebEngine（已包含在锁定依赖中）及运行中的本地 ComfyUI。桥接已针对本机 ComfyUI 0.20.1 / 前端 1.42.15 验证；升级前端后如桥接接口变化，仍需做兼容验证。

### 旧工作流移植

“工作流编辑”页增加了“本地工作流库”，选择条目后点击“打开选中工作流”。列表标明基础依赖是否齐全；连接或刷新模型时重新对照本机节点、模型和输入图片。缺少依赖的工作流仍可打开编辑，补齐之前不应提交生成。

本机 Local Comfy 活动目录的三套侧视角色工作流已复制到 `data/workflows/imported`，索引为 `data/workflows/library.json`；源文件保持不变并记录 SHA-256，相关标准姿态图保存在各副本的 `assets` 子目录。基础工作流已按原参数完成 768×1024、28 步出图；另两套缺少姿态 ControlNet 和部分服务端输入图。姿态图副本可通过 LoadImage 上传；角色参考图需另行选择。

移植记录位于 `data/migration-report.json`，实际加载与出图证据位于 `data/migration-acceptance.json`。用户工作流、素材和生成结果保留本地，由 `.gitignore` 排除。换电脑后可重新导入：

```powershell
& .\.venv\Scripts\python.exe -m tools.migrate_local_workflows --source '你的 ComfyUI 工作流目录' --asset-root '可选的姿态图目录'
```

该工具只复制顶层 UI JSON、复制被引用且能找到的配套图片、登记来源并检查依赖，不下载模型或改写 ComfyUI。源内容相同且本地副本未变时重复导入不会重复创建；源或副本已改动时创建新版本。

原有 AIGAMING 与 ComfyUI 工作流未被覆盖；没有下载模型、没有安装自定义节点。仅新增标准 ComfyUI 生成输出和本软件数据。

## 测试与验收

在本目录 PowerShell 运行：

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
& .\.venv\Scripts\python.exe -m tests.live_smoke
& .\.venv\Scripts\python.exe -m tests.live_editor
```

`live_smoke` 需要运行中的 ComfyUI 和现有 SDXL 权重，会实际执行 768×768、20 步生成，打开真实 Qt 窗口，经窗口的入队逻辑提交，验证下载图片和 QPixmap 预览，保存 `data/acceptance.json` 与 `data/acceptance-desktop.png`。`live_editor` 验证内嵌节点编辑、UI/API 转换和编辑器提交出图，记录在 `data/editor-acceptance.json`。两者都会消耗 GPU 时间并产生图片。

第一阶段验收：连接返回真实 checkpoint；任务进入 ComfyUI 队列；采样进度随事件变化；界面仍可操作；最终图片可预览且 PNG/参数/工作流落盘；重启可浏览结果。取消应只影响本软件当前任务；错误显示在日志并写入 job.json。

手动复查：重复添加两次任务观察串行完成；增加步数后取消当前任务；关闭 ComfyUI 后刷新观察连接错误；另存图片并打开；生成完成后释放显存。程序有后台操作时会阻止立即关闭，避免销毁工作线程，需先取消并等待。

阶段二验收目标：导入已授权数据集→预处理/标注→独立环境完成一轮真实 LoRA 训练→模型版本登记→在第一阶段生成测试图。

阶段三验收目标：编辑保存骨架→关键帧插值→姿态控制真实出图→检查角色一致性和抖动→逐帧修改→导出 PNG/Sprite Sheet/GIF/MP4。

阶段四验收目标：独立视频工作流真实生成→首尾帧与参数可复现→预览导出→验证 12GB 显存策略和取消/错误处理。

模块设计见 `docs/ARCHITECTURE.md`。GitHub 创建步骤见 `docs/GITHUB.md`。
