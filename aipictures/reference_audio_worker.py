"""Decode only saved H3 audio after the private sampler has exited."""
import json
import os
import sys
from pathlib import Path


def main():
    request=json.loads(Path(sys.argv[1]).read_text('utf-8'))
    if sys.stdin.readline().strip()!='go':raise SystemExit('Decode was not admitted')
    os.environ['FREEVIDEO_HOME']=request['root'];sys.path.insert(0,request['source'])
    from freevideo_engine.paths import add_vdn
    add_vdn()
    import torch
    import numpy as np
    from freevideo_engine.vae_weights import load_audio_vae
    value=np.load(request['latent'],allow_pickle=False)
    if value.ndim!=4 or value.shape[:3]!=(1,32,2) or not np.isfinite(value).all():raise ValueError('Invalid saved audio latent')
    device=request.get('device','cpu')
    if device!='cpu':raise ValueError('Post-generation audio decode uses CPU only')
    torch.set_num_threads(4)
    latent=torch.from_numpy(value).permute(0,2,1,3).reshape(2,32,-1).to(device)
    vae,_=load_audio_vae(request['base'],device=device)
    mean=torch.tensor(vae.config.latents_mean,device=device).view(1,32,1)
    std=torch.tensor(vae.config.latents_std,device=device).view(1,32,1)
    with torch.inference_mode():audio=vae.decode(latent*std+mean,return_dict=False)[0].float().permute(1,0,2)[0].cpu().numpy()
    if audio.ndim!=2 or audio.shape[0]!=2 or not np.isfinite(audio).all():raise ValueError('Invalid decoded audio')
    target=Path(request['out']);target.parent.mkdir(parents=True,exist_ok=True);np.save(target,audio,allow_pickle=False)
    print(json.dumps(dict(ok=True,sample_rate=32000,samples=audio.shape[1],device=device)),flush=True)


if __name__=='__main__':main()
