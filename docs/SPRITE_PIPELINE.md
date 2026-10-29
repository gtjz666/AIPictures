# 离散精灵帧管线

这是一套**后处理与资源打包**工具，不运行 AI，也不把视频相邻帧混合。仓库是桌面应用，不是 ComfyUI 自定义节点，因此没有强行依赖 ComfyUI。独立包只需 Pillow、NumPy、PyYAML；无需 Qt、PyTorch 或显卡。

软件中：完成动画后，点击播放控制栏的 **导出像素素材…**。选择像素格、单帧画布、色数、锚点与留白，指定 ZIP 地址。导出包含单帧、精灵图、metadata、配置和验收报告，并打开最近邻精灵图预览。普通“导出动画…”保留原有非像素输出。

新生成的完整骨骼动画会额外保存 `frame_NNN/matte_native.png`：这是前景分割后的原生尺寸帧，在旧版放大、区域校色和修复之前保存。像素导出优先读取它；不会覆盖原图或原工作流。旧缓存没有这些文件时使用原结果，并在报告中说明既有处理不可逆。

## 安装与命令

仓库已有环境可以直接运行 `python -m sprite_pipeline`。独立安装只装这个包，不会安装整个桌面应用：

```powershell
python -m pip install ".[test]"
sprite_pipeline --help
```

以下命令在仓库根目录执行，路径含空格请加引号。先创建生成阶段约束，再执行全管线：

```powershell
python -m sprite_pipeline config --out pipeline.yaml --seed 4242 --anchor "anchor.png" --canvas-width 96 --canvas-height 128 --palette-size 24 --pixel-size 8 --padding 2 --columns 4 --fps 8
python -m sprite_pipeline config --check pipeline.yaml
python -m sprite_pipeline run "input_frames" --out "out" --config pipeline.yaml
python -m sprite_pipeline validate --out "out"
```

不使用锚点图时省略 `--anchor`。JSON 与 YAML 均支持；相对锚点路径相对于配置文件所在目录。`config` 要求固定 seed，不接受 `-1`；后处理本身可以不记录 seed，但会警告。它**仅记录/校验约束**，不会重新生成，不能证明 AI 遵循了参考图或种子。生成时应在现有软件中设置同一参考图和固定 seed，并保留实际工作流。

也可以逐步执行六个命令：

```powershell
python -m sprite_pipeline snap "input_frames" --out out --config pipeline.yaml --pixel-size auto
python -m sprite_pipeline normalize "out/frames" --out out --config pipeline.yaml
python -m sprite_pipeline palette "out/frames" --out out --config pipeline.yaml
python -m sprite_pipeline assemble "out/frames" --out out --config pipeline.yaml
python -m sprite_pipeline validate --out out --config pipeline.yaml
python -m sprite_pipeline config --check pipeline.yaml
```

不显式传配置时，后续命令会继承 `out/pipeline.json`。命令行参数覆盖配置。不要并发写同一输出目录。输入只读，输出应使用独立目录；分步操作明确允许输入 `out/frames`。为防止覆盖，输出目录里未登记为本管线所有的 PNG 会导致报错。

## 配置

```yaml
canvas_width: 96
canvas_height: 128
anchor_mode: bottom-center
palette_size: 24
pixel_size: 8
seed: 4242
anchor: anchor.png
padding: 2
columns: 4
rows: null
fps: 8
alpha_threshold: 128
allow_scale: false
manual_offset: [0, 0]
drift_threshold: 1.0
palette_distance_threshold: 0.08
```

- **像素捕捉**：确定性的中位切分 K 色量化，然后每格按非透明覆盖率和主色取样；只沿 x/y 轴把夹在主色间的少量过渡色归并到已有邻色，不进行全局平滑。`8` 表示源图每 `8×8` 格成为一个真实像素，不是将小图模糊放大再缩回。透明度按阈值二值化，报告原半透明像素数。边长不能整除时末格按实际覆盖率处理。
- **自动像素格**：从锚点或第一帧的轴向边缘能量自相关估计，整段共用同一网格，格子起点为图片左上角。证据不足回退 1 并警告。周期纹理可能误判；不规则网格、倾斜画面、普通插画建议明确指定格大小。错位网格应先裁切/对齐输入；锚点与序列分辨率差异大时尤其应手动指定。`1` 仅量化和局部色归并，不能恢复已丢失细节。
- **画布**：尺寸指捕捉后的真实像素尺寸。默认不缩放主体，只移动/补透明边。超出画布时报错；只有 `--allow-scale` 才可最近邻缩小，并记录缩放比。不同帧各自缩小可能改变角色比例，优先增大画布。
- **bottom-center**：alpha bbox 底边中心贴画布底部中心。bbox 使用右/下边界不含端点的坐标。奇偶宽度差可能产生最多半像素中心差，实际只作整数平移。
- **bbox-center**：轮廓中心贴画布中心。**manual**：保留原始画布坐标，统一平移 `manual_offset: [dx, dy]`，不会逐帧重新贴底。跳跃/移动动画请选 manual，否则贴底会消除高度轨迹。任何非透明内容被裁掉都会报错。
- **调色板**：优先从锚点可见像素提取；没有锚点则从整段共同提取。按 sRGB 最近色映射，无抖色，透明像素不参与统计。色数限制是非透明 RGB 色数。不同颜色区域仍可能被模型画错，近邻映射没有语义分区能力。
- **拼图**：自然排序 `frame_1, frame_2, frame_10`。行列可指定一个或两个，留空自动计算；指定的网格容不下帧数时报错。padding 包含外围和格间透明留白，不向邻格扩散颜色。

## 输出与验收

```text
out/
  frames/*.png          # 二值透明、统一尺寸的独立素材
  sprite_sheet.png
  sprite_sheet.json     # 帧矩形、来源及 SHA-256、锚点、色板、FPS、实际参数
  palette.json
  pipeline.json         # 可重复使用的配置
  pipeline-state.json   # 分步处理记录
  report.json
```

`report.json` 检查尺寸、色数、共享色板、二值 alpha、切片逐像素回读及帧顺序；锚点 bbox 漂移超限发 warning，输出与锚点调色板距离超限则验收失败。另报告相邻帧颜色使用集合的 Jaccard 差异、映射前色差和缺失 seed / 锚点等警告。色差单位为 RGB 欧氏距离除以 `255√3`，范围 0–1；不是感知色差或身份相似度。

源码与依赖验收扫描 **sprite_pipeline 包的可执行导入/调用及运行依赖清单**，排除 FXAA/TAA/DLSS 和已知全局/历史混合调用；不是对整个旧桌面应用的任意混淆代码进行形式化证明。像素管线仅使用最近邻，不使用超分、时间混合或全局抗锯齿。

退出码：`0` 成功（可能有警告）；`1` 验收失败；`2` 输入/配置错误。结构通过不能证明 AI 没有多余肢体、换装、漂移花纹或错误动作，不能据此宣称接近 100% 的生成准确率。阴影、尾巴或飘动衣物会改变 bbox；需要语义脚部锚点时应调整生成/骨骼或使用统一手动偏移。

输入没有透明背景时会警告并保留背景，**不会猜测哪些颜色应删除**。请先使用软件的前景分割或提供透明 PNG；否则背景会进入色板。二值透明与少色量化会损失原有半透明效果、细线和渐变，这是像素素材的显式转换，不能替代普通高清资产导出。

## 复验

```powershell
python -m pytest tests/test_sprite_pipeline.py tests/test_sprite_assets.py tests/test_motion_clip.py -q
python -m pytest tests -q
python -m tools.demo_sprite_pipeline
python -m tests.live_sprite_export_controls
```

合成测试覆盖模糊块/灰边、自动网格及回退、半透明阈值、三帧偏移对齐、三帧轻微偏色、自然排序/留白/精灵图回读、篡改检测、重复运行确定性、配置错误、越界与原始文件保护、原生透明帧导出及可移动 ZIP。demo 是合成测试图，**不是 AI 生成效果证明**。Qt 检查确认默认不缩放、独立设置窗口与最近邻预览。

本机已完成 130 项单元测试及 7 个参数子用例；另通过像素导出、手选 LoRA、参考保真/断线恢复三组 Qt 检查。独立包构建安装成功，并在仓库外通过安装后的 `sprite_pipeline` 命令完成合成帧全流程与验收，无需启动 ComfyUI。
