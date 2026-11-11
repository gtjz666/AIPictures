"""Reuse completed music latents to compare FP32 decode devices; no music resampling."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import wave
import numpy as np


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--proof',type=Path,required=True);args=parser.parse_args()
    args.proof.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((args.source/'audio.json').read_text('utf-8'));config=manifest['params']['audio_settings']
    sys.path.insert(0,config['source']);os.environ['FREEVIDEO_HOME']=config['engine_root']
    from freevideo_engine.locking import runtime_lock
    with runtime_lock(Path(config['engine_root'])/'engine.lock',inherit=False,wait_seconds=0):
        import torch
        from aipictures.audio_clarity import install
        from freevideo_engine.music.pipeline import load,write_wav
        install(args.proof);torch.cuda.reset_peak_memory_stats();start=time.monotonic()
        pipeline=load(config['model_root'],device='cuda',mode='staged');latents=torch.from_numpy(np.load(args.source/'audio-latents.npy'))
        with torch.inference_mode(),pipeline._component('vae') as vae:
            audio=pipeline._decode(vae,latents).float();peak=audio.abs().amax(dim=[1,2],keepdim=True)
            if torch.any(peak>1):audio=audio/peak.clamp(min=1)
            audio=audio[0].cpu();audio=audio.clone()*(10**(-1/20)/audio.abs().max())
        elapsed=time.monotonic()-start;write_wav(args.proof/'decoded.wav',audio)
        with wave.open(str(args.source/'audio-master.wav'),'rb') as src:old=np.frombuffer(src.readframes(src.getnframes()),dtype='<i2').reshape(-1,2).T.astype(np.float32)/32768
        now=audio.numpy();assert now.shape==old.shape and np.isfinite(now).all()
        result=dict(vae_only=True,no_new_music_sampling=True,seconds=now.shape[1]/48000,elapsed_seconds=elapsed,
            gpu_peak_bytes=torch.cuda.max_memory_allocated(),mean_abs_difference=float(np.abs(now-old).mean()),max_abs_difference=float(np.abs(now-old).max()),
            source=str(args.source.resolve()),policy=json.loads((args.proof/'clarity-policy.json').read_text('utf-8')))
        assert result['mean_abs_difference']<.001 and result['max_abs_difference']<.01,'Decoder devices diverged'
        (args.proof/'acceptance.json').write_text(json.dumps(result,indent=2),'utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
