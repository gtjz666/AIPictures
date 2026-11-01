"""Select a near-closed cycle from actual frames; never crossfade or synthesize pixels."""
from pathlib import Path

import numpy as np
from PIL import Image


def cycle_indices(paths: list[Path], count: int) -> tuple[list[int], dict]:
    if count<2 or len(paths)<=count:
        raise ValueError('循环提取需要比输出帧数更多的源帧。')
    samples=[]
    for path in paths:
        with Image.open(path) as source:
            # Analysis thumbnails only. The selected output files remain untouched.
            rgba=np.asarray(source.convert('RGBA').resize((48,64),Image.Resampling.NEAREST),dtype=np.float32)/255.
        alpha=rgba[:,:,3]
        if np.min(alpha)>.95:
            background=np.median(np.concatenate((rgba[0,:,:3],rgba[-1,:,:3],rgba[:,0,:3],rgba[:,-1,:3])),axis=0)
            alpha=(np.max(np.abs(rgba[:,:,:3]-background),axis=2)>.06).astype(np.float32)
        rgba[:,:,3]=alpha
        samples.append(rgba)
    frames=np.stack(samples)
    minimum=max(count,len(paths)//3)
    best=None
    def distance(a,b):
        mask=(a[:,:,3]>.5)|(b[:,:,3]>.5)
        if not mask.any(): return 1.
        rgb=float(np.mean(np.abs(a[:,:,:3][mask]-b[:,:,:3][mask])))
        aa,bb=a[:,:,3]>.5,b[:,:,3]>.5
        shape=1.-float(np.sum(aa&bb))/max(1,int(np.sum(aa|bb)))
        return .65*rgb+.35*shape
    for start in range(max(1,len(paths)-minimum)):
        for end in range(start+minimum,len(paths)):
            seam=distance(frames[start],frames[end])
            # Matching direction through the seam avoids a pose match at a reversal.
            v0=(frames[start+1]-frames[start]).ravel()
            v1=(frames[end]-frames[end-1]).ravel()
            denominator=float(np.linalg.norm(v0)*np.linalg.norm(v1))
            velocity=float(np.dot(v0,v1)/denominator) if denominator>1e-8 else 0.
            score=seam+.02*(1.-max(-1.,min(1.,velocity)))
            candidate=(score,-(end-start),start,end,seam,velocity)
            if best is None or candidate<best: best=candidate
    _,_,start,end,seam,velocity=best
    indices=[round(start+i*(end-start)/count) for i in range(count)]
    variation=float(np.mean(np.std(frames[indices,:,:,:3],axis=0)))
    warnings=[]
    if seam>.12: warnings.append('首尾姿态或配色差异较大，循环接缝需检查。')
    if velocity<-.25: warnings.append('首尾附近的运动方向差异较大，请检查循环处是否顿挫。')
    if variation<.002: warnings.append('帧间动作变化很小，请确认没有生成静止画面。')
    return indices,{'method':'nearest_real_cycle_no_blending','start':start,'endpoint':end,
        'source_indices':indices,'endpoint_duplicate_excluded':True,'seam_score':round(seam,5),
        'velocity_similarity':round(velocity,5),'motion_variation':round(variation,6),
        'warnings':warnings,'guaranteed_seamless':False}
