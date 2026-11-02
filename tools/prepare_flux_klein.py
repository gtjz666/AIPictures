"""Install the two pinned Klein assets; reuse the verified installed Z-Image encoder."""
import argparse
from pathlib import Path
from urllib.request import ProxyHandler, build_opener, install_opener

from aipictures.storage import DATA, write_json
from .prepare_style_models import install_file, digest

REV = '5b3abca5c0dc1ecd4eaf3340868d09063fc1c965'
FILES = (
    ('diffusion_models', 'flux-2-klein-4b.safetensors', 7751105712,
     'ec3d4e733a771f61c052fb4856c48b336c55eaf2c65487c2a1faeb9bbda7a343'),
    ('vae', 'flux2-vae.safetensors', 336211292,
     '868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3'),
)
ENCODER_SHA = '72450b19758172c5a7273cf7de729d1c17e7f434a104a00167624cba94f68f15'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comfy-root', type=Path, required=True)
    parser.add_argument('--proxy')
    args = parser.parse_args()
    root = args.comfy_root.resolve()
    if not (root / 'main.py').is_file():
        raise ValueError('请选择已安装的ComfyUI目录。')
    encoder = root / 'models/text_encoders/qwen_3_4b_fp8_mixed.safetensors'
    if not encoder.is_file() or digest(encoder) != ENCODER_SHA:
        raise ValueError('缺少已验证的Qwen3 4B编码器；请先安装本软件的Z-Image组件，不覆盖其他同名文件。')
    if args.proxy:
        install_opener(build_opener(ProxyHandler({'https': args.proxy, 'http': args.proxy})))
    records = []
    for category, name, size, checksum in FILES:
        records.append(install_file(root / 'models' / category / name, {
            'bytes': size, 'sha256': checksum,
            'url': f'https://huggingface.co/Comfy-Org/Flux-2-Klein-4B/resolve/{REV}/split_files/{category}/{name}'}))
        write_json(DATA / 'flux-klein-installation.json', {
            'revision': REV, 'files': records, 'new_bytes': sum(r['bytes'] for r in records),
            'reused_encoder': str(encoder), 'reused_encoder_sha256': ENCODER_SHA})
    print('FLUX_KLEIN_ASSETS_READY', flush=True)


if __name__ == '__main__':
    main()
