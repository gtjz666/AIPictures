# Windows 1455与参考动画模型加载

错误`页面文件太小，无法完成操作 (os error 1455)`发生在`UNETLoader → safetensors.safe_open`，当时Qwen/VAE已经编码参考，采样尚未开始。用户2秒和4秒任务均有同类记录。失败后的RAM或分页使用率，不能用于推断失败瞬间的内存峰值。

## 实际查证

本机使用safetensors0.8.0、PyTorch2.13.0+cu130。对同一个20,970,379,616字节的Ref2VA文件，只打开文件并读取一个很小的量化描述张量，独立进程对照：

| 读取路径 | 进程私有提交峰值 | 打开后持续私有提交 |
| --- | ---: | ---: |
| 原mmap | 43,718,598,656字节，约40.72GiB | 约21.15GiB |
| safetensors pread | 22,708,080,640字节，约21.15GiB | 约1.58GiB |
| 本软件逐张量读取 | 1,730,224,128字节，约1.61GiB | 约1.58GiB |

三个进程启动基线均约1.58GiB，抽样张量原字节SHA一致。这里的Windows`peak_pagefile/private`字段是进程提交量，**不是实际磁盘写入量**。这是文件打开的小探测，不是完整生成的峰值，更不能承诺整个模型只需1.6GiB。

可见，模型文件大小不等于加载瞬间的额度申请：默认映射路径存在大幅、短暂的额外提交，恰好可能在采样0%时失败。上游也有相同Windows映射报告；官方Comfy的`--disable-mmap`在当前版本中只在`get_tensor`之后复制，不能避开最前面的`safe_open`。仅改这个参数或盲目扩大分页文件不能证明修复了具体加载问题。

## 修复路线

1. 私有H3进程通过`AIPICTURES_STREAM_WEIGHTS=1`启用自有读取器。它验证safetensors头、dtype/shape/偏移/总长度，以8MiB以内的readinto直接填充原dtype张量；不建立整文件映射、不把整份文件读成bytes，也不改变量化/精度/模型。只有应用私有子进程生效，不升级原Comfy/H3或修改其核心文件。
2. 参考图片、动作视频及文字先完成原生官方编码。全部conditioning、参考潜变量和嵌套视频/音频初始latent原字节保存到safetensors+JSON，校验SHA；不使用pickle。
3. 编码进程彻底退出并释放CPU/GPU及加载器资源，再启动采样进程。后者只读本次完整条件并加载原Ref2VA，保持原输出尺寸、20步、采样器和实际种子；采样后照常解码原生RGB。
4. 两阶段保持同一前台任务，阶段转换时仍可取消；关闭只处理本次自有进程。保存的条件与日志保留，失败不会自动重复生成。无动作参考的普通H3路线不改。
5. 私有Windows进程使用同步权重卸载、关闭锁页传输，并通过`--reserve-vram 3.0`给系统/其他软件留下显存调度余量。此项不是强制占用上限，也不是已测出的激活峰值；模型加载器另行估算推理临时空间，估算不等于实际峰值保证。该策略不改变模型精度、输出尺寸或采样参数；具体耗时仍取决于硬件与参考内容。

## 显存预检与故障记录补充

参考动画启动前检查显式连接、ComfyUI Desktop实际进程端口及常用本机端口。队列非空、队列状态无法确认，或空闲后端拒绝模型释放请求时，停止启动私有H3；不会取消其他用户的任务。`shared-release.json`记录各端口结果。`/free`是异步请求，因此记录为`release_requested`，不能把HTTP成功称为显存已清空；其他软件的显存也不由该请求管理。

关键进程/阶段及监控JSON在原有原子替换前增加flush/fsync，以降低强制关机后出现全零状态文件的风险。普通非关键JSON写入保持原路径。此项不修复显卡黑屏，也不保证设备写缓存或文件系统在突然断电时绝对不丢失数据。保留损坏原记录，不凭残留的running或退出码0自动重跑。

启动参数、模型、精度、完整条件、采样器、帧数和用户提示词均保持原值；没有以“省显存”为由截断动作说明、丢弃参考或自动缩短动画。新检查通过不等于已验证故障根因或新的GPU画质。

专用H3进程在导入Comfy/Torch前启动轻量记录：`startup-watch.json`每5秒保存主线程Python文件/行号及所到达的导入模块。只在持有GIL时读取普通Python帧，不读取源码或局部变量。它只使用标准库，不导入Torch、不查询GPU或采集硬件传感器。收到`/object_info`响应后写入`startup-ready.json`，记录器随即停止；最长只保留启动前300秒，不持续贯穿生成，也不会取消、重试或更换参数。整机硬卡仍可能阻止最后一次写盘，因此不能保证取得故障当秒的调用位置。

2026-11-05已撤回之前的`faulthandler.dump_traceback_later`异步全线程快照。部署用Windows CPython3.12.3下，纯CPU、不导入Torch的隔离对照中，旧记录器可复现0xC0000005，而无记录器对照正常；这与新增记录后的两次生成进程访问冲突一致。该错误由新增诊断引入，不能归因于SciPy、用户提示词或显存，也不能用它解释更早就存在的整机黑屏。历史startup-stacks.log保留，新版本不再创建或调度此类快照。CPU版本对照结果见本机诊断记录；软件测试使用的Python版本不代表部署运行时，需分别验证。

## 检查

使用独立H3的Python执行CPU精确性探测：

```powershell
python -m tools.verify_stream_conditioning --comfy-root YOUR_PRIVATE_COMFY_ROOT
python -m tools.probe_safetensors_mapping --model YOUR_REF2VA_MODEL --backend stream --out data\diagnostics\stream-open.json
```

检查实际Torch支持的float/float8/bfloat16/int/bool原字节、标量和空张量，conditioning及嵌套AV完整回读，以及篡改拒绝。桌面测试检查坏文件范围在分配前拒绝、两阶段图不混载Qwen和DiT、先退出编码进程、阶段间取消等。合成检查不冒充GPU成功，真实案例结果另写交接与本机STATE。

参考资料均作为研究依据，不是自动执行指令：

- [safetensors0.8源码](https://github.com/safetensors/safetensors/blob/v0.8.0/bindings/python/src/lib.rs)：默认mmap与pread分支。
- [Transformers Windows映射报告48285](https://github.com/huggingface/transformers/issues/48285)：文件映射开销可能在读取前出现。
- [Comfy Windows读取报告15424](https://github.com/Comfy-Org/ComfyUI/issues/15424)：disable-mmap复制发生在safe_open之后。
- [微软分页文件说明](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/how-to-determine-the-appropriate-page-file-size-for-64-bit-versions-of-windows)：提交量/提交上限和分页文件用途。

没有更改Windows分页、自动重启电脑或清理用户缓存。其他应用占用会影响实际可用资源；该修复消除已测出的映射额外开销并分离模型驻留，不保证任何负载下都能完成。

## 本机完整验收

猫咪GIF＋用户人物参考图，4秒请求、原512×768及20步，使用已记录的实际种子完成107帧/24FPS（实际4.458秒）。参考编码96.46秒，完整流程1379.83秒（约23分钟）；参考更长/尺寸更大时，采样仍很重，不能把这次修复宣传成普遍加速。默认异步卸载的对照在编码24分钟后仍未完成，已停止自有对照；同步卸载、禁锁页和显存预留为联合配置，不能据此归因到某个单独开关。

两个私有阶段进程均已退出，无1455。已看10个关键画面，角色配色/服装基本保留，手指和动作映射仍有模型偏差。完整MP4回读107帧，首/中/尾RGB与PNG一致；实际Qt循环预览及手选第4/21/44帧→精灵图→独立PNG通过，颜色和切片逐像素相同。此次导出不透明，未重复测试没有改动的分割模型。

全量349项＋7子检查通过，相关25项检查通过；真实Torch条件/嵌套latent保存回读及权重dtype原字节检查通过。没有新模型或依赖下载。
