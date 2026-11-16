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
        for path in sorted((ADDON.parent/'docs/images').glob('runner-*.png')):
            archive.write(path,'images/'+path.name)
    return dict(path=str(output),bytes=output.stat().st_size,sha256=digest(output))


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('dist/AlI-Godot-addon.zip'));args=parser.parse_args()
    print(json.dumps(package(args.output)))
