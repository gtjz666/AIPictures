"""Private, gated Sony Woosh worker. One request, then all models exit."""
import json
import math
import os
from pathlib import Path
import sys
import time


def main():
    value=json.loads(Path(sys.argv[1]).read_text('utf-8'))
    if sys.stdin.readline().strip()!='go':raise SystemExit('Sound-effect worker was not admitted')
    sys.path[:0]=[value['source'],value['runtime_source']]
    from freevideo_engine.locking import runtime_lock
    with runtime_lock(Path(value['engine_root'])/'engine.lock',inherit=False,wait_seconds=0):
        import torch
        import numpy as np
        import soundfile as sf
        from woosh.components.base import LoadConfig
        from woosh.model.ldm import LatentDiffusionModel
        from woosh.inference.flowmatching_sampler import flowmatching_integrate
        os.chdir(value['source']);torch.set_num_threads(4);torch.manual_seed(value['seed'])
        torch.cuda.reset_peak_memory_stats();start=time.monotonic()
        model=LatentDiffusionModel(LoadConfig(path=str(Path(value['source'])/'checkpoints'/'Woosh-Flow'))).eval()
        for conditioner in model.conditioners.values():
            tokens=conditioner.tokenizer(value['caption'],truncation=False)['input_ids']
            if len(tokens)>77:raise ValueError('音效要求超出模型文字窗口，请精简声音事件；未截断后生成。')
        # Keep official FP32 inference and decoder precision; batch is always one.
        model=model.to('cuda')
        frames=math.ceil(value['seconds']*100)+1
        with torch.inference_mode():
            noise=torch.randn(1,128,frames,device='cuda')
            condition=model.get_cond(dict(audio=None,description=[value['caption']]),no_dropout=True,device='cuda')
            latent,steps=flowmatching_integrate(model,noise=noise,cond=condition,cfg=4.5,atol=.001,rtol=.001,
                return_steps=True,device='cuda',dtype=torch.float64)
            audio=model.autoencoder.inverse(latent).cpu().float().numpy().reshape(-1)
        count=round(value['seconds']*48000)
        if len(audio)<count or not np.isfinite(audio).all():raise ValueError('Invalid or short Woosh output')
        audio=audio[:count];peak=float(np.max(np.abs(audio)));rms=float(np.sqrt(np.mean(audio.astype('float64')**2)))
        if rms<.00001:raise ValueError('Woosh produced near-silent output')
        gain=min(1.,.98/max(peak,.000001));audio=audio*gain
        sf.write(value['out'],audio,48000,subtype='PCM_24')
        print(json.dumps(dict(ok=True,engine='Sony Woosh-Flow',sample_rate=48000,channels=1,samples=count,
            steps=steps,elapsed_seconds=round(time.monotonic()-start,3),peak_before=peak,peak_gain=gain,rms=rms,
            gpu_peak_bytes=torch.cuda.max_memory_allocated(),dtype='float32',torch=torch.__version__)),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        import traceback
        traceback.print_exc();print(json.dumps(dict(ok=False,detail=str(exc))),flush=True);raise SystemExit(1)
