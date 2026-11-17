"""Package only the editor addon and its user guide, never weights or machine settings."""
import argparse
import zipfile
from pathlib import Path
from aipictures.godot_assets import ADDON
from aipictures.workflow_library import digest


def package(output):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ADDON/'addons/ali_assets').iterdir()):
            if path.is_file() and path.suffix in ('.gd','.cfg'):
                archive.write(path,'addons/ali_assets/'+path.name)
        archive.write(ADDON.parent/'docs/GODOT_ASSETS.md','README.md')
        archive.write(ADDON.parent/'docs/GODOT_BLUEPRINTS.md','GODOT_BLUEPRINTS.md')
        archive.write(ADDON.parent/'docs/GODOT_RUNNER_GUIDE.md','GODOT_RUNNER_GUIDE.md')
        from .render_game_guide import render_guide
        archive.writestr('使用步骤.html',render_guide(ADDON.parent/'docs/GODOT_RUNNER_GUIDE.md'))
        catalog=ADDON.parent/'docs/GODOT_BLUEPRINT_CATALOG.md'
        technical=ADDON.parent/'docs/GODOT_BLUEPRINT_TECHNICAL.md'
        archive.write(technical,'GODOT_BLUEPRINT_TECHNICAL.md')
        archive.writestr('蓝图技术文档.html',render_guide(technical,title='AlI 蓝图技术文档',navigation_title='技术目录'))
        stage=ADDON.parent/'docs/BLUEPRINT_05_PLAN.md'
        archive.write(stage,'BLUEPRINT_05_PLAN.md')
        archive.writestr('蓝图0.5阶段文档.html',render_guide(stage,title='AlI 蓝图0.5第一阶段',navigation_title='阶段目录'))
        archive.write(ADDON.parent/'docs/images/blueprint-programming.png','images/blueprint-programming.png')
        archive.write(catalog,'GODOT_BLUEPRINT_CATALOG.md')
        archive.writestr('蓝图模块手册.html',render_guide(catalog,title='AlI 蓝图模块手册',navigation_title='模块目录'))
        archive.write(ADDON.parent/'docs/images/blueprint-character.png','images/blueprint-character.png')
        for path in sorted((ADDON.parent/'docs/images').glob('runner-*.png')):
            archive.write(path,'images/'+path.name)
    return dict(path=str(output),bytes=output.stat().st_size,sha256=digest(output))


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('dist/AlI-Godot-addon.zip'));args=parser.parse_args()
    print(json.dumps(package(args.output)))
