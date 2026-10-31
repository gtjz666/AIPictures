"""Shared foreground palette for previews; no frame blending or PNG alteration."""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree


def save_gif(images, target, fps, loop=False, size=(384,512)):
    samples=[]
    for image in images:
        array=np.asarray(image.convert('RGBA'));samples.append(array[:,:,:3][array[:,:,3]>200][::4])
    colors=np.concatenate(samples) if any(len(s) for s in samples) else np.zeros((1,3),dtype=np.uint8)
    colors=colors[np.linspace(0,len(colors)-1,min(65536,len(colors)),dtype=int)]
    palette=Image.fromarray(np.resize(colors,(256,256,3))).quantize(colors=255,method=Image.Quantize.MEDIANCUT)
    table=palette.getpalette();table=table+[0]*(768-len(table))
    tree=cKDTree(np.asarray(table,dtype=float).reshape(-1,3)[:255]);previews=[]
    for image in images:
        small=image.convert('RGBA').resize(size,Image.Resampling.LANCZOS)
        quantized=small.convert('RGB').quantize(palette=palette,dither=Image.Dither.NONE)
        indices=np.array(quantized);reserved=indices==255
        if reserved.any():indices[reserved]=tree.query(np.asarray(small)[:,:,:3][reserved])[1]
        indices[np.asarray(small.getchannel('A'))<128]=255
        preview=Image.fromarray(indices);preview.putpalette(table);previews.append(preview)
    # GIF time uses centiseconds. Distribute rounding instead of speeding up 8 FPS.
    durations=[max(10,10*(round((i+1)*100/fps)-round(i*100/fps))) for i in range(len(images))]
    previews[0].save(Path(target),save_all=True,append_images=previews[1:],duration=durations,
        disposal=2,transparency=255,optimize=False,**({'loop':0} if loop else {}))
