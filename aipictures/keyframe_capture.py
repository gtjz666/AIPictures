"""Select actual action landmarks, then fill temporal gaps with actual source frames."""
from pathlib import Path

import numpy as np
from PIL import Image


def keyframe_indices(paths: list[Path], count: int,
                     times: list[float] | None = None) -> tuple[list[int], dict]:
    if count<2 or len(paths)<count:
        raise ValueError('关键帧捕捉需要至少与输出帧数相同的源帧。')
    clock=np.asarray(times if times is not None else list(range(len(paths))),dtype=np.float64)
    if len(clock)!=len(paths) or not np.isfinite(clock).all() or np.any(np.diff(clock)<=0):
        raise ValueError('源帧时间必须有限且严格递增。')
    features=[]
    for path in paths:
        with Image.open(path) as image:
            rgba=np.asarray(image.convert('RGBA').resize((24,32),Image.Resampling.NEAREST),dtype=np.float32)/255.
        alpha=rgba[:,:,3]
        if np.min(alpha)>.95:
            border=np.concatenate((rgba[0,:,:3],rgba[-1,:,:3],rgba[:,0,:3],rgba[:,-1,:3]))
            background=np.median(border,axis=0)
            alpha=(np.max(np.abs(rgba[:,:,:3]-background),axis=2)>.06).astype(np.float32)
        # Silhouette dominates. RGB helps recognize articulated poses with the same bbox.
        # These thumbnails are analysis data only, never used for output pixels.
        features.append(np.concatenate((alpha.ravel(),(.25*rgba[:,:,:3]*alpha[:,:,None]).ravel())))
    values=np.stack(features)
    keys={0,len(paths)-1}
    budget=min(count,max(3,count//2))
    while len(keys)<budget:
        best=None
        ordered=sorted(keys)
        for left,right in zip(ordered,ordered[1:]):
            if right-left<2:continue
            ids=np.arange(left+1,right)
            weight=(clock[ids]-clock[left])/(clock[right]-clock[left])
            predicted=values[left]+weight[:,None]*(values[right]-values[left])
            errors=np.mean((values[ids]-predicted)**2,axis=1)
            pick=int(np.argmax(errors))
            candidate=(float(errors[pick]),int(ids[pick]))
            if best is None or candidate>best:best=candidate
        if best is None or best[0]<1e-6:break
        keys.add(best[1])
    chosen=set(keys)
    while len(chosen)<count:
        gaps=[(clock[b]-clock[a],a,b) for a,b in zip(sorted(chosen),sorted(chosen)[1:]) if b-a>1]
        _,left,right=max(gaps)
        midpoint=(clock[left]+clock[right])/2
        chosen.add(min(range(left+1,right),key=lambda i:abs(clock[i]-midpoint)))
    return sorted(chosen),{'method':'key_poses_then_real_inbetweens','key_source_indices':sorted(keys),
        'source_indices':sorted(chosen),'synthesized_frames':False,'warnings':[
            '关键帧按轮廓和画面变化估计；镜头运动、遮挡或背景变化可能干扰识别。']}
