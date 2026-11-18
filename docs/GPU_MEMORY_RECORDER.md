# 显存记录器

用户于2026-11-06明确要求持续记录显存，以便排查生成时/完成后黑屏。2026-11-18再次授权检查两次黑屏及资源堆积；现有记录也包含Windows系统内存和提交量，用于区分显存压力与内存压力。不开启压力测试，不采集温度或频率，不更改驱动、电源或超频设置。

双击根目录「启动显存记录.bat」。记录器在后台运行，关闭AlI后继续记录，可覆盖生成完成几分钟后才出问题的情况；重启电脑后需要打开AlI或再次启动记录。启用后的本机设置会让AlI启动时自动恢复一个记录器；双击「停止显存记录.bat」会停止并关闭此自动恢复。不会安装系统服务、登录启动项或计划任务。

每约1秒记录一次NVIDIA设备总显存、已用、可用、GPU标识和驱动版本，以及Windows可用物理内存、当前提交量和提交上限；不加载Torch/CUDA、不加载模型、不分配推理显存、不读取温度或频率。界面有任务时同步记录任务目录、阶段和进度，不记录提示词或Key。旧版本界面正在运行时仍可发现近期任务、读取有限错误日志；软件重新打开后才能提供新的界面上下文。超过5秒未更新的界面PID、阶段和进度不再绑定给新发现的任务，`context_source=task_files`明确表示只根据任务文件取证。

任务完成不会停止监测。记录器还会读取实际编码/采样步数和后端退出记录，并只读检查其中的PID是否仍存在；切到下一任务时保留尚存活的旧PID供核对，不自动杀进程。Windows可能复用PID，仅“PID仍存在”不能证明模型泄漏。H3编码/采样子进程的正常退出有上下文管理和Job保护；普通单图的共享Comfy可能保留模型缓存，播放器循环也仍有显示开销，二者不等于持续推理。是否存在逐次累积，要结合多次生成的进程与显存曲线判断，不能只凭静态代码或一次空闲值保证。

采集子进程调用官方只读NVML，记录主进程不调用驱动。一次最多一个请求；驱动查询超过1.5秒就记录超时并继续写心跳，保留同一个待完成请求，不叠加进程或请求。程序不会因占用高自动取消、重启、重试生成或修改驱动/供电。

- 可用显存≤512MiB或占用≥95%：高压力预警。
- 可用显存≤128MiB或占用≥99%：极高压力预警。
- 仅任务明确出现CUDA/Torch显存不足错误时标为allocation_oom_reported。OS1455分页文件不足、CUDA unknown、GPU占用高都不能自动判成GPU OOM；即使尚有可用显存，也可能发生大块分配失败。

日志在 `data/diagnostics/gpu-watch/时间_会话/`。JSONL逐条flush/fsync；每8MiB切换新文件，旧记录不删除。每秒小记录通常是每天数十MB，进程持续到手动停止或系统结束。`current.json`提供当前/上次会话和峰值，也在原子替换前flush/fsync；正常停止时写`summary.json`。`gpu-monitor.bat report`生成`report.json`，包含首尾采样、显存峰值、最低可用内存、提交量峰值与上限、至多256条后端阶段记录。状态文件缺失或损坏时，自动选择最后采样的会话生成报告，原损坏文件保留；不会因今天查看旧报告而选错最近会话。报告忽略损坏末行，不把无停止尾记直接当作崩溃证明。

CLI：

```powershell
.venv\Scripts\python.exe -m aipictures.gpu_watch start --data .\data
.venv\Scripts\python.exe -m aipictures.gpu_watch status --data .\data
.venv\Scripts\python.exe -m aipictures.gpu_watch stop --data .\data
.venv\Scripts\python.exe -m aipictures.gpu_watch report --data .\data
```

限制：Windows WDDM下NVML通常不能提供可靠的逐进程显存分配量，因此这里只报告设备总计，不能把其他软件占用全算给AlI。1秒采样可能漏掉瞬时峰值；如果驱动/系统完全挂死或掉电，最终采样及硬盘缓存仍可能丢失。该功能收集证据，不保证防止黑屏，也不能从一个高占用值确定根因。GPU标识保持可跨重启比对，但数据不上传。

官方依据：[NVML设备查询](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceQueries.html)、[NVIDIA SMI及WDDM限制](https://docs.nvidia.com/deploy/nvidia-smi/index.html)。
