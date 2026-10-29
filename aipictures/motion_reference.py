"""Human detection first; explicit silhouette estimates for other biped character layouts."""
import json
from pathlib import Path

from PIL import Image,ImageOps
import numpy as np

from .background import foreground_rgba,release_session
from .character_profile import JOINT_NAMES,LIMBS
from .reference_analysis import prepare_reference,PoseNotApplicable,opaque_reference
from .storage import DATA,write_json
from .workflow_library import digest


def silhouette_rig(rgba):
    box=rgba.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()
    if box is None: raise ValueError('参考图没有可用主体。')
    x,y,right,bottom=box; width=right-x; height=bottom-y
    # Compact biped proportions, all relative to this image; no borrowed character coordinates.
    positions=[(.72,.16),(.58,.34),(.49,.39),(.42,.56),(.45,.70),
        (.58,.39),(.56,.56),(.57,.70),(.50,.77),(.52,.87),(.52,.96),
        (.60,.77),(.63,.87),(.64,.96),(.70,.13),(.72,.13),(.55,.17),(.57,.17)]
    joints={name:[x+u*width,y+v*height,.6 if i not in (5,6,7,11,12,13,15,17) else .35]
        for i,(name,(u,v)) in enumerate(zip(JOINT_NAMES,positions))}
    return {'schema_version':4,'canvas':[768,1024],'direction':'right','source_direction':'right',
        'ground_y':bottom,'rig_id':'compact_biped_silhouette_v1','joints':joints,'limbs':[list(v) for v in LIMBS],
        'annotation':'silhouette_estimate','notes':'未检出人体，按本图主体范围估计双足布局。非测量关节；建议校准，不适用于四足或无足主体。'}


def prepare_motion_reference(reference,client,emit=lambda *_:None,cancel=None):
    import threading
    cancel=cancel or threading.Event(); checksum=digest(reference)
    root=DATA/'motion-analysis'/('v2_'+checksum[:20]); metadata=root/'analysis.json'
    if metadata.is_file():
        result=json.loads(metadata.read_text('utf-8'))
        if all(Path(result[name]).is_file() for name in ('rgba','opaque','rig')): return result
    try:
        result=prepare_reference(reference,client,emit,cancel)
        result=dict(result,layout='detected_biped',layout_note='按参考图识别的双足骨架，遮挡侧为估计。')
    except PoseNotApplicable:
        emit('reference_stage',{'message':'未检出人体；按此图估计卡通双足布局，可在骨骼窗口校准。'})
        root.mkdir(parents=True,exist_ok=True)
        with Image.open(reference) as image: rgba=foreground_rgba(image,cancel)
        box=rgba.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()
        if box is None: raise ValueError('参考图主体为空。')
        subject=rgba.crop(box); scale=min(900/subject.height,500/subject.width)
        subject=subject.resize((round(subject.width*scale),round(subject.height*scale)),Image.Resampling.LANCZOS)
        offset=((768-subject.width)//2,978-subject.height)
        geometry={'source_bbox':list(box),'scale':scale,'offset':list(offset),
            'subject_bbox':[offset[0],offset[1],offset[0]+subject.width,978]}
        canvas=Image.new('RGBA',(768,1024)); canvas.paste(subject,offset)
        alpha=np.asarray(canvas.getchannel('A')); ys,xs=np.nonzero(alpha>24)
        top,bottom=int(ys.min()),int(ys.max()); height=max(1,bottom-top)
        head=xs[ys<top+height*.30]; body=xs[(ys>top+height*.42)&(ys<top+height*.72)]
        direction='left' if len(head) and len(body) and np.median(head)<np.median(body) else 'right'
        if direction=='left': canvas=ImageOps.mirror(canvas)
        canvas.save(root/'reference_rgba.png'); opaque_reference(canvas).save(root/'reference_rgb.png')
        rig=silhouette_rig(canvas); rig['source_direction']=direction; write_json(root/'rig.json',rig)
        result={'source':str(reference),'source_sha256':checksum,'rgba':str(root/'reference_rgba.png'),
            'opaque':str(root/'reference_rgb.png'),'rig':str(root/'rig.json'),'geometry':geometry,
            'direction':direction,'direction_estimated':True,
            'layout':'estimated_compact_biped','layout_note':rig['notes']}
    release_session(); write_json(metadata,result); return result
