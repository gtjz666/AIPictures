"""Install only AIPictures' own optional node; never overwrite ComfyUI core files."""
import argparse
import shutil
import time
from pathlib import Path


def install(comfy_root: Path) -> Path:
    root = Path(comfy_root).resolve()
    if not (root/'main.py').is_file():
        raise ValueError('请选择包含 main.py 的 ComfyUI 根目录。')
    source = Path(__file__).resolve().parents[1]/'comfy_nodes'/'aipictures_runtime'/'__init__.py'
    target = root/'custom_nodes'/'AIPicturesRuntime'/'__init__.py'
    if not target.resolve().is_relative_to((root/'custom_nodes').resolve()):
        raise ValueError('节点目标路径越界。')
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file() and target.read_bytes()!=source.read_bytes():
        shutil.copy2(target,target.with_name('__init__.py.'+time.strftime('%Y%m%d_%H%M%S')+'.bak'))
    shutil.copy2(source,target)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--comfy-root',type=Path,required=True)
    print(install(parser.parse_args().comfy_root))
