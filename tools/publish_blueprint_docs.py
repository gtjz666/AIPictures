"""Create a portable, versioned Blueprint documentation folder and addon ZIP."""
import argparse
import html
import json
import shutil
from pathlib import Path
from .render_game_guide import render_guide
from .package_godot_addon import package

PAGES=(
    ('DINO_AI_ASSETS_TUTORIAL.md','小恐龙跑酷制作教程.html','小恐龙跑酷完整制作教程'),
    ('GODOT_SCENE_BLUEPRINT_GUIDE.md','场景蓝图教程.html','场景蓝图与更换素材参考'),
    ('TRANSPARENT_FRAME_EXPORT.md','动画帧导出指南.html','PNG 序列和精灵图导出参考'),
    ('BLUEPRINT_05_PLAN.md','蓝图0.5阶段文档.html','0.5完整2D使用步骤与验收'),
    ('GODOT_BLUEPRINT_TECHNICAL.md','蓝图技术文档.html','运行架构、数据格式与兼容策略'),
    ('GODOT_BLUEPRINT_CATALOG.md','蓝图模块手册.html','蓝图模块与参数索引'),
    ('GODOT_BLUEPRINTS.md','角色蓝图指南.html','角色蓝图操作'),
    ('GODOT_ASSETS.md','素材导出指南.html','Godot素材与插件安装'),
    ('MOSS_IMAGE.md','画面设计说明.html','画面设计使用说明'),
)


def publish(output):
    root=Path(__file__).resolve().parents[1];source=root/'docs'
    output=Path(output).resolve()
    # Do not merge into an unrelated user folder or overwrite older evidence.
    output.mkdir(parents=True,exist_ok=False)
    images=output/'images';images.mkdir()
    for path in sorted((source/'images').glob('*.png')):
        if path.name.startswith(('blueprint-','runner-','moss-','ali-guide-')):shutil.copy2(path,images/path.name)
    for filename,target,title in PAGES:
        shutil.copy2(source/filename,output/filename)
        (output/target).write_text(render_guide(source/filename,title='AlI · '+title,navigation_title='目录'),'utf-8')
    specification=source/'BLUEPRINT_05_REQUIREMENTS.md'
    if specification.exists():
        shutil.copy2(specification,output/specification.name)
        (output/'0.5完整需求基线.html').write_text(render_guide(specification,title='AlI Blueprint 0.5 完整需求基线',navigation_title='需求目录'),'utf-8')
    links=''.join('<li><a href="'+html.escape(target)+'">'+html.escape(title)+'</a></li>' for _,target,title in PAGES)
    index='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AlI 蓝图0.5文档</title><style>body{max-width:900px;margin:50px auto;padding:24px;font:17px/1.9 "Microsoft YaHei",sans-serif;color:#193c43;background:#f3f8f7}a{color:#236c69}li{margin:14px 0}article{padding:32px;background:white;border-radius:12px}</style><article><h1>AlI 蓝图0.5文档</h1><p>AlI Blueprint 0.5 · Godot 4.6</p><p>第一次制作游戏请打开第一项，从新建基础场景一路做到试玩和替换素材。其他页面供查阅。</p><ol>'''+links+'''</ol><p><a href="0.5完整需求基线.html">查看完整升级需求（需求不代表已实现）</a></p><p><a href="AlI-Godot-addon-0.5.zip">插件安装包</a> · <a href="https://github.com/gtjz666/AIPictures">GitHub仓库</a></p><p>旧自含场景请创建新名称升级，原场景与运行副本保留。所有HTML均可离线阅读；Markdown原文和所需图片同目录保留。</p></article></html>'''
    (output/'开始阅读.html').write_text(index,'utf-8')
    (output/'README.txt').write_text('先打开“开始阅读.html”。这是0.5完整适用2D功能的技术文档与插件包。按用户最新要求，3D／2.5D系统暂缓制作。\n','utf-8')
    receipt=package(output/'AlI-Godot-addon-0.5.zip')
    (output/'文档清单.json').write_text(json.dumps(dict(version='0.5.0',addon=receipt,files=sorted(p.name for p in output.iterdir())),ensure_ascii=False,indent=2),'utf-8')
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(publish(args.output))
