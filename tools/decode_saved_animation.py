"""Decode a saved Comfy latent with the existing VAE; never rerun sampling."""
import argparse
import json
from pathlib import Path
import shutil
import threading
from uuid import uuid4

from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.storage import write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--latent',type=Path,required=True)
    p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();root=a.input_root.resolve()
    if not root.is_dir() or not a.latent.is_file():raise ValueError('请提供已存在的 ComfyUI 输入目录与生成潜变量文件。')
    a.out.mkdir(parents=True,exist_ok=True)
    client=ComfyClient();cleanup=release_idle_models(client)
    name='aipictures_recovery_'+uuid4().hex+'.latent'
    shutil.copy2(a.latent,root/name)
    graph={'load':{'class_type':'LoadLatent','inputs':{'latent':name}},
        'vae':{'class_type':'VAELoader','inputs':{'vae_name':'wan_2.1_vae.safetensors'}},
        'decode':{'class_type':'VAEDecode','inputs':{'samples':['load',0],'vae':['vae',0]}},
        'save':{'class_type':'SaveImage','inputs':{'images':['decode',0],'filename_prefix':'AIPictures/detail_vae_recovery'}}}
    write_json(a.out/'workflow.json',graph)
    write_json(a.out/'source.json',{'saved_latent':str(a.latent.resolve()),'resampled':False,'cache_cleanup':cleanup})
    result=client.generate(graph,a.out,lambda k,d:print(k,d,flush=True) if k in ('queued','executing') else None,
        threading.Event(),timeout=float('inf'),submitted=lambda pid:write_json(a.out/'submitted.json',{'prompt_id':pid}))
    write_json(a.out/'result.json',result)
    print(json.dumps({'prompt_id':result['prompt_id'],'frames':len(result['images']),'resampled':False}),flush=True)
    release_idle_models(client)


if __name__=='__main__':main()
