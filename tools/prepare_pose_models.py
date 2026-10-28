"""Pinned Wan Animate motion model; reuse existing Wan encoder/VAE and CLIP Vision H."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tools.prepare_style_models import install_file
from aipictures.storage import DATA,write_json

MODEL='Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors'
MODEL_SPEC={'bytes':18401760586,'sha256':'2936b31473a967e7a429a6646bba60e7862d0938e178b58b2a140f391dd5b8e6',
 'url':'https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/033a4e487f60220b3d6e469599a6aebc46e13cee/Wan22Animate/'+MODEL}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--models',required=True); args=parser.parse_args()
    root=Path(args.models).resolve()
    # Frozen metadata recorded from the publisher; SHA-256 is verified before install.
    lora='lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors'
    spec={'bytes':738005744,'sha256':'85c4a61c30e0497aa44b91d93a893b624708461a56fe5485183b28fa07e2dfb3',
      'url':'https://huggingface.co/Kijai/WanVideo_comfy/resolve/8260d429d19fd7a72304cad059160b95d843913f/Lightx2v/'+lora}
    jobs=[(root/'diffusion_models'/MODEL,MODEL_SPEC),(root/'loras'/'AIPictures'/'animation'/lora,spec)]
    with ThreadPoolExecutor(max_workers=2) as pool: records=list(pool.map(lambda job:install_file(*job),jobs))
    write_json(DATA/'pose-model-installation.json',{'files':records,'bytes':sum(r['bytes'] for r in records)})
    print('Motion models verified and installed.',flush=True)


if __name__=='__main__': main()
