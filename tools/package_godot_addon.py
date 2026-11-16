"""Package only the editor addon and its user guide, never weights or machine settings."""
import argparse
import zipfile
from pathlib import Path
from aipictures.godot_assets import ADDON
from aipictures.workflow_library import digest


def package(output):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('plugin.cfg','plugin.gd','asset_drag.gd','blueprint_model.gd','blueprint_window.gd','custom_module_template.gd'):
            archive.write(ADDON/'addons/ali_assets'/name,'addons/ali_assets/'+name)
        archive.write(ADDON.parent/'docs/GODOT_ASSETS.md','README.md')
        archive.write(ADDON.parent/'docs/GODOT_BLUEPRINTS.md','GODOT_BLUEPRINTS.md')
    return dict(path=str(output),bytes=output.stat().st_size,sha256=digest(output))


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('dist/AlI-Godot-addon.zip'));args=parser.parse_args()
    print(json.dumps(package(args.output)))
