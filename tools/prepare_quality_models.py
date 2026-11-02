"""Historical optional offline translator installer; SDXL weights are retired."""
import argparse
from pathlib import Path

from .prepare_style_models import install_file
from aipictures.storage import DATA, write_json

MODELS = Path('D:/ComfyModels')
REVISION = 'cf419233522daa0b9ea36c3aff98fa2cab1fb0fb'
TRANSLATOR_REVISION = 'cf109095479db38d6df799875e34039d4938aaa6'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models',type=Path,default=MODELS)
    parser.add_argument('--translator-only',action='store_true')
    parser.add_argument('--translation-python',type=Path,required=True,
                        help='Existing independent Python with torch, transformers and sentencepiece')
    args = parser.parse_args()
    if not args.translation_python.is_file():
        raise ValueError('翻译用 Python 不存在，请指定已有 ComfyUI 或独立翻译环境的 python.exe。')
    root = args.models/'translation'/'opus-mt-zh-en'
    base = f'https://huggingface.co/Helsinki-NLP/opus-mt-zh-en/resolve/{TRANSLATOR_REVISION}/'
    records = []
    for name,size,checksum in (
        ('config.json',1394,None),('generation_config.json',293,None),
        ('source.spm',804677,None),('target.spm',806530,None),
        ('tokenizer_config.json',44,None),('vocab.json',1617902,None),
        ('pytorch_model.bin',312087009,'9d8ceb91d103ef89400c9d9d62328b4858743cf8924878aee3b8afc594242ce0')):
        # Small files are pinned by immutable revision; record their actual hashes too.
        records.append(install_file(root/name,{'url':base+name,'bytes':size,'sha256':checksum}))
    write_json(DATA/'translator-settings.json',{'model_dir':str(root),
        'python':str(args.translation_python.resolve()),
        'enabled':True,'timeout_seconds':60,'model_revision':TRANSLATOR_REVISION})
    # SDXL checkpoint installation retired at the user's request. This historical
    # entry point can still prepare the independent optional CPU translator.
    write_json(DATA/'quality-model-installation.json',{'records':records,'automatic_lora_selection':False})
    print('Pinned quality assets installed.',flush=True)


if __name__=='__main__':
    main()
