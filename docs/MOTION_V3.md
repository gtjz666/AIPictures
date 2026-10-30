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

## 工作流改变

旧 8 帧导出使用 17 张姿态输入，时间压缩后约 5 个运动潜帧。原生模式改为 33 张输入、约 9 个运动潜帧；16 帧导出采用 65 张输入、约 17 个运动潜帧。目标是让每张离散资产获得更细的时间条件，实际效果必须通过生成对照判断，不能仅凭潜帧数宣称准确性必然提升。快速预览保持较少输入。

这不是后期补帧或历史帧混合。模型先生成完整连续帧，再按完整动作相位选择单帧。仍使用原生 768×1024、20 步、CFG 1 和同一模型/VAE，采样与解码分阶段，去背景在生成后进行，默认保留生成 RGB。不引入 FXAA/TAA/DLSS 或全局锐化。

跳跃和下蹲采用包含终点的时间轴并单次播放，保存站立终点；走路、跑步、待机排除重复终点并循环。每张帧的具体动作阶段写入元数据。

## 验证方法

自动检查覆盖 129 个连续采样点的骨长、支撑脚、走路始终至少一脚落地、跑步两次腾空、下蹲低位停留与双脚固定，以及 8 / 16 帧的原生条件数量。实际测试固定同一参考、seed、画布、模型、采样器和 20 步，对照旧版结果；本次同时改变骨骼与时间采样，因此不能把差异单独归因于其中一项。

```powershell
python -m pytest -q
python -m tests.live_animation_modes
python -m tests.live_cancel_close
python -m tools.verify_animation_modes --reference "参考图.png" --out data/action-v3 --actions walk idle run jump squat
```

真实测试结果在 `data/animation-motion-v3/20261030_native`。检查生成与导出完成、可见 RGB 保留、PNG 与精灵图回读，并逐帧目视复查角色和服装。完整生成通过与外观完全一致是不同验收项；GIF 仅用于预览，PNG 是完整色彩的游戏素材。
