"""Pinned official Z-Image assets, compatible with the existing ComfyUI model family."""
import argparse
from pathlib import Path
from .prepare_style_models import install_file
from aipictures.storage import DATA,write_json

REV='6fc90a3b1b653e935a0d175e260736de25b84df5'
FILES=(
 ('vae','ae.safetensors',335304388,'afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38'),
 ('text_encoders','qwen_3_4b_fp8_mixed.safetensors',5631994051,'72450b19758172c5a7273cf7de729d1c17e7f434a104a00167624cba94f68f15'),
 ('diffusion_models','z_image_turbo_bf16.safetensors',12309866400,'2407613050b809ffdff18a4ac99af83ea6b95443ecebdf80e064a79c825574a6'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--comfy-root',type=Path,required=True);a=p.parse_args()
    if not (a.comfy_root/'main.py').is_file():raise ValueError('ComfyUI root is invalid.')
    records=[]
    for category,name,size,checksum in FILES:
        records.append(install_file(a.comfy_root/'models'/category/name,{'bytes':size,'sha256':checksum,
            'url':f'https://huggingface.co/Comfy-Org/Z-Image-Turbo/resolve/{REV}/split_files/{category}/{name}'}))
        write_json(DATA/'zimage-model-installation.json',{'records':records,'revision':REV})
    print('ZIMAGE_ASSETS_READY',flush=True)


if __name__=='__main__':main()
