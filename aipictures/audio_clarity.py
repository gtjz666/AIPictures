"""Task-local ACE policy: retain the approved caption and decode in full precision."""
def install(folder=None,decoder_device='auto'):
    import torch
    from freevideo_engine.music import pipeline,lm
    construct=pipeline._construct
    def full_precision_decoder(kind,root,weights,device,dtype):
        if kind!='vae':return construct(kind,root,weights,device,dtype)
        target=device
        if decoder_device=='cpu' or torch.device(device).type!='cuda':target='cpu'
        elif decoder_device=='auto' and torch.cuda.mem_get_info()[0]<6*1024**3:target='cpu'
        if folder:
            import json
            from pathlib import Path
            (Path(folder)/'clarity-policy.json').write_text(json.dumps(dict(vae_precision='float32',vae_device=str(target),approved_caption_retained=True)),'utf-8')
        return construct(kind,root,weights,target,torch.float32)
    pipeline._construct=full_precision_decoder
    decode=pipeline.MusicPipeline._decode
    def decode_float(self,vae,latents):
        latents=latents.to(device=next(vae.parameters()).device,dtype=torch.float32)
        if folder:
            import numpy as np
            from pathlib import Path
            np.save(Path(folder)/'audio-latents.npy',latents.cpu().numpy())
        return decode(self,vae,latents)
    pipeline.MusicPipeline._decode=decode_float
    generate=lm.InstrumentalLM.generate
    def preserve(self,caption,seconds,*args,**kwargs):
        metadata,codes,times=generate(self,caption,seconds,*args,**kwargs)
        metadata=dict(metadata,caption=caption)
        return metadata,codes,times
    lm.InstrumentalLM.generate=preserve
