# AlI 当前技术文档入口

2026年11月18日 · 蓝图0.5.0（2D） · 实测Godot4.6。

本轮统一实现全部适用2D需求：通用动画、真实串并行、UI、TileMapLayer、Camera2D、参数子图、输入与音频、跨场景服务、设置存档，以及四类框架和六类原生界面。保留旧流程，3D／2.5D暂缓。

建议按以下顺序阅读：

首次实际生成素材搭建跑酷，请先看[小恐龙完整菜单与AI素材测试步骤](DINO_AI_ASSETS_TUTORIAL.md)：从单张参考、透明动画帧、声音到0.5原生菜单的具体接入，不需要重建项目。

1. [0.5使用步骤与验收范围](BLUEPRINT_05_PLAN.md)
2. [完整技术文档：数据格式、执行语义与兼容策略](GODOT_BLUEPRINT_TECHNICAL.md)
3. [全部模块与参数：71类游戏／13类角色](GODOT_BLUEPRINT_CATALOG.md)
4. [角色蓝图操作](GODOT_BLUEPRINTS.md)
5. [跑酷小游戏制作步骤](GODOT_RUNNER_GUIDE.md)
6. [素材导出与Godot插件安装](GODOT_ASSETS.md)
7. [画面设计使用说明](MOSS_IMAGE.md)
8. [原始0.5完整需求及最新范围修订](BLUEPRINT_05_REQUIREMENTS.md)

原始需求保留包括暂缓3D的原文，当前范围以使用步骤为准。旧自含游戏场景须另建新名称升级，不覆盖原文件。示例素材用于机制验证，不能当作新AI生成质量证明。

可在仓库根目录运行以下命令，生成包含离线HTML、Markdown、图片和插件ZIP的独立文档文件夹；输出目录须为新目录：

```text
python -m tools.publish_blueprint_docs --output <新的文档文件夹>
```
