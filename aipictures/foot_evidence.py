"""Conservative image-space foot-height evidence for isolated, flat-background actors."""
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def foot_heights(path: Path) -> dict | None:
    with Image.open(path) as source:
        rgb=np.asarray(source.convert('RGB'),dtype=float)
    h,w=rgb.shape[:2]
    if h<24 or w<24:return None
    border=np.concatenate((rgb[:2].reshape(-1,3),rgb[-2:].reshape(-1,3),rgb[:, :2].reshape(-1,3),rgb[:,-2:].reshape(-1,3)))
    background=np.median(border,axis=0)
    if (np.abs(border-background).max(axis=1)<16).mean()<.9:return None
    mask=np.abs(rgb-background).max(axis=2)>55
    yy,xx=np.where(mask)
    if len(yy)<50:return None
    top,bottom=int(yy.min()),int(yy.max());left,right=int(xx.min()),int(xx.max())
    actor_height=bottom-top+1
    # Work only in the lowest band; upper-body parts must never become feet.
    y0=max(top,bottom-round(actor_height*.08))
    region=mask[y0:bottom+1,left:right+1].copy();components=[]
    for y,x in zip(*np.where(region)):
        if not region[y,x]:continue
        queue=deque([(int(y),int(x))]);region[y,x]=False;points=[]
        while queue:
            cy,cx=queue.popleft();points.append((cy,cx))
            for ny,nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
                if 0<=ny<region.shape[0] and 0<=nx<region.shape[1] and region[ny,nx]:
                    region[ny,nx]=False;queue.append((ny,nx))
        if len(points)>=max(4,actor_height*.03):components.append(points)
    components=sorted(components,key=len,reverse=True)
    if len(components)!=2:return None
    a,b=sorted(components,key=lambda points:np.mean([x for y,x in points]))
    if not .3<=len(a)/len(b)<=3:return None
    ay=max(y for y,x in a)+y0;by=max(y for y,x in b)+y0
    threshold=max(2,actor_height*.012)
    state='left_up' if ay<by-threshold else 'right_up' if by<ay-threshold else 'both_down'
    return dict(method='isolated-lower-components',left_bottom=ay,right_bottom=by,
                threshold=threshold,state=state,note='画面坐标高度证据，不判断地面接触或解剖左右')
