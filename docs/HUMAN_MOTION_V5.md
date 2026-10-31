# 真人运动参考与 LoRA 走路对照

## 新动作控制

跳跃、基础攻击的新建骨骼采用版本 5。先从真人动作中提取侧面关节方向、相对重心和接触时序，再按当前角色的骨长重建，最后使用现有 Wan Animate 工作流生成。没有训练新模型。

- 跳跃参考 CMU `16_05` 的向前跳跃：屈髋屈膝、重心后移、脚趾蹬地、摆臂、腾空伸屈腿、落地吸收和恢复。取消上一版强制跑步式分腿。PNG 不包含整段腾空位移，跳跃高度由游戏引擎控制；`jump_game_preview.gif` 仅为同一组 PNG 添加显示位移。
- 攻击参考 CMU `14_01` 的一段拳击：后脚小步打开站姿，前脚尖作为定位锚点；后脚蹬地抬跟，髋与肩胸配合出拳，另一手防守，收拳后回步。命中处加入短暂停顿，手部仍使用已有的 21 点握拳控制。
- 支撑脚通过 IK 保持自身骨长；脚跟抬起时保留脚尖接触。攻击的后脚离地回步，避免两只平脚向两侧滑开。动作方向会随参考图朝向处理。
- 已保存的图片不会重生成。旧版已手动编辑的骨骼保留；未编辑的自动预设在新任务或编辑时升级。版本 4 的曲线和动作提示仍可回放，便于比较。

`sequence.json` 记录 `motion_revision` 与真人曲线来源；`motion.json` 保存本次角色的实际完整骨骼。`game_animation.json` 的跳跃起落阶段和攻击有效阶段按骨骼版本输出。阶段下标是美术标记，游戏碰撞需另行设置。

## 研究来源与转换

The data used in this project was obtained from mocap.cs.cmu.edu.

使用 [CMU Graphics Lab Motion Capture Database](http://mocap.cs.cmu.edu/) 的 subject 16 / motion 05（向前跳跃）及 subject 14 / motion 01（拳击）。原 ASF/AMC 共约 4.7 MB，保存在本地研究缓存。运行时只读取两份紧凑曲线表；表中含来源、校验值、投影方向和时序映射。源数据的使用条件见 [曲线来源与授权说明](../aipictures/resources/human_motion/NOTICE.md)，不将转换后的捕捉数据作为独立商品出售。

运动分析参考 [Animation Mentor 的身体运动讲解](https://www.animationmentor.com/blog/animation-tips-tricks-what-makes-or-breaks-a-good-body-mechanics-shot/)：先决定重心与发力，再安排身体各部分的先后。ASF/AMC 解释依据 [University of Wisconsin 格式说明](https://research.cs.wisc.edu/graphics/Courses/cs-838-1999/Jeff/ASF-AMC.html)。本项目对真人曲线做二维投影、时长调整和接触约束，这是为横版素材作的适配。

离线复现转换（需要自行取得上述原始捕捉文件，不访问 ComfyUI）：

```powershell
python -m tools.research_mocap --subject 16 --motion 16_05
python -m tools.research_mocap --subject 14 --motion 14_01
python -m tools.build_human_motion_curves
```

原始文件位于 `data/motion-research/cmu/16.asf`、`16_05.amc`、`14.asf`、`14_01.amc`。ASF 解析器用于本次 CMU 文件研究，不是支持所有 Acclaim 导出变体的通用导入器。

## 手动 LoRA 风格对照

界面中导入参考图，选择“动画序列帧 → 走路”，勾选“按手动选择的 LoRA 改变参考画风”，再在风格窗口选择类型、LoRA 和强度。未勾选时继续使用参考最小修改路线，不自动分析或选择风格。

SDXL LoRA 接入 SDXL 图生图与 IP-Adapter，先生成风格基准，再重新检测骨骼，送入 Wan Animate。换风格优先呈现 LoRA 的风格，头发、服装和颜色可能变化。

以下命令用同一参考、固定 seed 和参数，串行生成“手绘动画 / 水彩 / 3D 角色”三组真实走路输出，每组保存风格基准、工作流、连续骨骼、8 张透明 PNG、精灵图和 GIF：

```powershell
python -m tools.verify_lora_walks --reference '参考图完整路径.png' --out data/lora-comparison-new --styles ghibli watercolor render-3d
```

每组使用新的子进程释放前一组的本地分割会话。工具中的外观描述是本次紫发角色的比较用例；软件提示词仍由用户填写。未知风格、缺失模型、未完成的旧任务和参数不同的已有结果均报错，不悄悄重复采样。允许复用的已完成结果必须通过来源、seed、LoRA 与强度核对。

## 验证

```powershell
python -m pytest -q
$env:QT_QPA_PLATFORM='offscreen'
python -m tests.live_platformer_controls
python -m tests.live_animation_modes
# 以下两种动作实际使用 GPU。为每轮检查使用新目录。
python -m tools.verify_animation_modes --reference '参考图完整路径.png' --out data/human-motion-new --actions jump attack
```

自动检查覆盖：129 个采样时刻的骨长、前脚尖固定、后脚回步与抬跟、跳跃预备和落地压缩、固定根部、关节连续性、旧版本回放、游戏阶段划分、拼图回读与透明导出。数值通过仅证明控制和导出按约定执行。真人来源不等于模型一定正确服从，仍需逐帧检查手脚、配色、身份和动作自然度。

没有启用全局自动抗锯齿、时间混合或自动超分。保留生成 RGB，生成完成后才去背景；GIF 的有限色和二值透明不改变原始 PNG。
