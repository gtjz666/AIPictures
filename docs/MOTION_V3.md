# V3 动作与精灵帧准确性

## 参考资料与采用范围

核查了秋叶相关公开入口；其 B 站页面请求受限，没有取得可核验的对应动画 JSON，不将第三方冠名整合包当作作者原版。以下改变依据可直接核对的模型作者、节点实现、官方模板和动作教学，不替换现有 ComfyUI 安装。

- [ComfyUI 官方 Wan Animate 指南](https://docs.comfy.org/tutorials/video/wan/wan2-2-animate)和[官方模板 JSON](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_wan2_2_14B_animate.json)：采用 Move 姿态迁移，参考外观与动作序列分开输入；不连接替换模式的背景视频和人物遮罩。核对 CLIP Vision 的 `crop=none`、模型/VAE 与实际执行图。公开模板的快速 LoRA、重打光和长视频拼接没有作为精灵图准确性开关直接加入。
- [Animation Mentor 跑步教程](https://www.animationmentor.com/blog/animating-dynamic-run-cycles/)：接触/承重、经过、蹬地、腾空，左右腿半周期，手臂与腿反向，身体重心及头胸延迟。本项目自行编写按比例缩放的运动曲线，没有复制视频帧或声称已训练动作模型。
- [Animation Mentor 预备动作](https://www.animationmentor.com/blog/anticipation-the-12-basic-principles-of-animation/)：跳跃增加预蹲、伸展蹬地和落地缓冲。
- [ACE 深蹲动作资料](https://www.acefitness.org/resources/pros/expert-articles/7356/how-to-squat-properly-body-type-breakdown-anatomy-considerations/)：髋部后移、髋膝协同、脚跟保持落地及随体型调整。仅用于动画姿态设计，不作为健身指导。
- [Wan 官方配置](https://github.com/Wan-Video/Wan2.2/blob/main/wan/configs/wan_animate_14B.py)：VAE 时间步幅为 4；空间步幅为 8。
- [Wan-Animate-2 原作者仓库](https://github.com/Wan-Video/Wan-Animate-2)：本次核实已经发布独立代码和权重，但它直接使用驱动视频，不能把本项目的彩色骨架图直接当作同一种输入；本机现有节点也没有该新模型的完整链路。本轮不更新共享后端、不混接新旧模型，没有新增模型下载。

## 骨骼改变

新动画类型为走路、待机、跑步、跳跃、下蹲。伸手从新建选择中移除，已有文件仍保留。

`motion_kinematics.py` 按参考腿长计算步幅和高度。走路采用较长的支撑期，脚保持地面接触；抬脚阶段有独立回摆轨迹。跑步使用关键角度、正向运动学、承重压缩和两个腾空阶段，再以逆向运动学校验骨长。支撑脚的高度不随躯干旋转被拖离地面。肩胯和头部配合幅度降低，避免无意义的横向抖动。

跳跃按准备、下蹲、蹬地、空中、落地和恢复站立分段，空中高度考虑画布余量，避免头部出框。下蹲按髋部后移、屈膝下降、低位停留和起身设计；双脚脚掌与脚踝保持落地，身体前倾保持视觉平衡。手臂从参考原始角度过渡，不强行把初始手臂改成垂直。

新生成骨骼版本为 3。已有手动关键帧保留，需要采用新预设时可选择“恢复自动周期”。该系统仍以双足侧视布局为主，不是对任意视角/体型的三维动作捕捉。

首轮真实跳跃发现第 4、5 帧头顶触边。原因是最初按眼睛/鼻尖高度估算腾空余量，没有计入头发：本图头发顶部为 y=78，眼部点约 y=159，原根部最大抬升约 88 像素，足以越过上沿。修正为读取参考主体轮廓，预留 40 像素上边距；本图最大根部抬升约 38 像素，并用空中屈膝收腿增加脚部离地幅度，不缩小角色、不改变其他动作的比例。新边界数据写入动作文件，旧动作的历史采样仍按旧字段回放；手动帧不自动重写，主动恢复自动周期时采用新限制。该约束不能保证生成模型永不超出骨骼，因此另对实际透明帧检查空白和贴边，并在软件完成消息中提示复查。

## 工作流改变

旧 8 帧导出使用 17 张姿态输入，时间压缩后约 5 个运动潜帧。原生模式改为 33 张输入、约 9 个运动潜帧；16 帧导出采用 65 张输入、约 17 个运动潜帧。目标是让每张离散资产获得更细的时间条件，实际效果必须通过生成对照判断，不能仅凭潜帧数宣称准确性必然提升。快速预览保持较少输入。

这不是后期补帧或历史帧混合。模型先生成完整连续帧，再按完整动作相位选择单帧。仍使用原生 768×1024、20 步、CFG 1 和同一模型/VAE，采样与解码分阶段，去背景在生成后进行，默认保留生成 RGB。不引入 FXAA/TAA/DLSS 或全局锐化。

跳跃和下蹲采用包含终点的时间轴并单次播放，保存站立终点；走路、跑步、待机排除重复终点并循环。每张帧的具体动作阶段写入元数据。

连续骨骼输入改用无损多页 TIFF，仍由现有原生 `LoadImage` 读取。本机实测将原 65 个载入/拼接节点换成 1 个载入节点，33 页逐像素相等，重复页与顺序均保留；没有重采样、混帧或新增节点依赖。测试记录为 `data/research/motion-v3/pose-batch-parity-ready/acceptance.json`。这是减少重复中间拼接的优化，没有据此宣称固定的内存或耗时降幅。

## 已保存采样的恢复

本次跑步采样完成后，后端在解码期间断开；日志没有给出足以确定原因的异常，不将其直接归因于过热或内存。重新打开同一 Desktop 实例后，读取校验过的原 `.latent`，只执行 VAE 解码和透明导出，得到全部 33 张原生帧。原失败任务与采样编号保留，未重新采样。

```powershell
python -m tools.recover_animation_export --sequence data/action-v3/run --decode-dir data/action-v3/run/video/decode-recovery
# 若这个新解码任务的连接中断，仅恢复同一任务，不再次提交：
python -m tools.recover_animation_export --sequence data/action-v3/run --decode-dir data/action-v3/run/video/decode-recovery --resume-decode
```

工具拒绝覆盖已有导出帧，检查采样编号及潜变量 SHA-256。共享后端有其他任务时不抢占，不自动重启后端。若后端重启后任务记录已丢失，`--resume-decode` 不会悄悄重新提交；需明确选择新的解码目录。恢复记录与耗时单独保存，不把中断期间算作模型计算时间。

## 验证方法

自动检查覆盖 129 个连续采样点的骨长、支撑脚、走路始终至少一脚落地、跑步两次腾空、下蹲低位停留与双脚固定，以及 8 / 16 帧的原生条件数量。实际测试固定同一参考、seed、画布、模型、采样器和 20 步，对照旧版结果；本次同时改变骨骼与时间采样，因此不能把差异单独归因于其中一项。

```powershell
python -m pytest -q
python -m tests.live_animation_modes
python -m tests.live_cancel_close
python -m tools.verify_animation_modes --reference "参考图.png" --out data/action-v3 --actions walk idle run jump squat
```

真实测试结果在 `data/animation-motion-v3/20261030_native`。检查生成与导出完成、可见 RGB 保留、PNG 与精灵图回读，并逐帧目视复查角色和服装。完整生成通过与外观完全一致是不同验收项；GIF 仅用于预览，PNG 是完整色彩的游戏素材。
