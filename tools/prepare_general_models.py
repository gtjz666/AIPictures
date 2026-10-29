"""Install pinned native ComfyUI Qwen editing models, without changing its environment."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import ProxyHandler, build_opener, install_opener

from aipictures.storage import DATA, write_json
from tools.prepare_style_models import install_file

FILES = [
    ('diffusion_models', 'Comfy-Org/Qwen-Image-Edit', 'f68ace85e60b4a02a323e394253731947657b7d2',
     'qwen_image_edit_2511_fp8mixed.safetensors', 20533762817,
     'c9fdc158e46d3b61ef75f21ae866ca2fe808bf4a53643120d1c1e87c19280a4e'),
    ('text_encoders', 'Comfy-Org/HunyuanVideo_1.5_repackaged', '1405a2b738c29b890cf6d03fc038d8d3e92eeed7',
     'qwen_2.5_vl_7b_fp8_scaled.safetensors', 9384670680,
     'cb5636d852a0ea6a9075ab1bef496c0db7aef13c02350571e388aea959c5c0b4'),
    ('vae', 'Comfy-Org/Qwen-Image_ComfyUI', '1f12b17be14c89b026c51a91d67c32f84bb047bc',
     'qwen_image_vae.safetensors', 253806246,
     'a70580f0213e67967ee9c95f05bb400e8fb08307e017a924bf3441223e023d1f'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--proxy')
    args = parser.parse_args()
    if args.proxy:
        install_opener(build_opener(ProxyHandler({'http': args.proxy, 'https': args.proxy})))
    def install(spec):
        folder, repo, revision, name, size, sha = spec
        url = f'https://huggingface.co/{repo}/resolve/{revision}/split_files/{folder}/{name}'
        return install_file(args.models / folder / name, {'url': url, 'bytes': size, 'sha256': sha})
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(install, FILES))
    write_json(DATA / 'general-model-installation.json', {'files': records, 'bytes': sum(r['bytes'] for r in records)})
    print('General editing models verified.', flush=True)


if __name__ == '__main__':
    main()
