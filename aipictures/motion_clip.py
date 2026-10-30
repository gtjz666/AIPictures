"""Character-sized biped motion clips. Complete cycles, named joints and editable feet."""
import math
from copy import deepcopy
from pathlib import Path

from PIL import Image,ImageDraw

from .character_profile import JOINT_NAMES,LIMBS,COLORS
from .storage import DATA,write_json
from .walk_cycle import walk_rig,knee_ik
from .animation_actions import ACTIONS,stage_label,ONE_SHOT_ACTIONS
from .motion_dynamics import enrich_body

FOOT_NAMES=('right_heel','right_toe','left_heel','left_toe')
JOINT_LABELS=dict(zip(JOINT_NAMES,('鼻尖','颈部','右肩','右肘','右腕','左肩','左肘','左腕',
 '右髋','右膝','右踝','左髋','左膝','左踝','右眼','左眼','右耳','左耳')))
JOINT_LABELS.update(right_heel='右脚跟',right_toe='右脚尖',left_heel='左脚跟',left_toe='左脚尖')


def clip_path(source_sha,action):
    if action not in ACTIONS or len(source_sha)!=64 or any(c not in '0123456789abcdef' for c in source_sha):
        raise ValueError('动作或参考图校验值无效。')
    return DATA/'motions'/f'{source_sha}_{action}.json'


def with_feet(base):
    rig=deepcopy(base); p=rig['joints']; ground=rig.get('ground_y',978)
    for side in ('right','left'):
        ankle=p[side+'_ankle']; height=max(12,ground-ankle[1]); length=max(32,min(110,height*1.6))
        p.setdefault(side+'_heel',[ankle[0]-length*.25,ground,1])
        p.setdefault(side+'_toe',[ankle[0]+length*.75,ground,1])
    return rig


def with_visual_bounds(base, analysis):
    """Attach source silhouette bounds without modifying cached rigs or proportions."""
    rig=deepcopy(base)
    bounds=analysis.get('geometry',{}).get('subject_bbox')
    if bounds is None:return rig
    if len(bounds)!=4 or not all(math.isfinite(float(v)) for v in bounds):
        raise ValueError('参考图主体边界无效，请重新分析参考图。')
    x0,y0,x1,y1=map(float,bounds)
    if x1<=x0 or y1<=y0:raise ValueError('参考图主体边界为空，请重新分析参考图。')
    if analysis.get('direction')=='left':
        width=rig.get('canvas',[768,1024])[0];x0,x1=width-x1,width-x0
    rig['visual_bounds']=[x0,y0,x1,y1]
    return rig


def feet_for_pose(rig,base,phase,action):
    p=rig['joints']; source=base['joints']
    for side,offset in (('right',0),('left',.5)):
        ankle=p[side+'_ankle']; original=source[side+'_ankle']
        # Each ankle owns exactly one heel and one toe; never duplicate an entire shoe pair.
        angle=0
        if action in ('walk','run') and not rig.get('contacts',{}).get(side,False):
            q=(phase+offset)%1
            angle=math.radians(18)*math.sin(math.tau*q)
        for part in ('heel','toe'):
            dx=source[side+'_'+part][0]-original[0]; dy=source[side+'_'+part][1]-original[1]
            p[side+'_'+part]=[ankle[0]+dx*math.cos(angle)-dy*math.sin(angle),
                ankle[1]+dx*math.sin(angle)+dy*math.cos(angle),1]
        floor=base.get('ground_y',978)
        lowest=max(p[side+'_heel'][1],p[side+'_toe'][1])
        if lowest>floor:
            for part in ('heel','toe'): p[side+'_'+part][1]-=lowest-floor
    return rig


def pose_at(base,phase,action='walk'):
    if action not in ACTIONS: raise ValueError('不支持的动作。')
    from .motion_kinematics import walk_pose,run_pose,squat_pose,jump_pose
    one_shot_end=action in ONE_SHOT_ACTIONS and phase>=1
    phase=phase%1
    base=with_feet(base)
    makers={'walk':walk_pose,'run':run_pose,'squat':squat_pose,'jump':jump_pose}
    rig=makers[action](base,phase) if action in makers else deepcopy(base)
    enrich_body(rig,base,phase,action)
    reported_phase=1 if one_shot_end else phase
    rig.update(action=action,phase=reported_phase,stage=stage_label(action,reported_phase),ground_y=base.get('ground_y',978))
    feet_for_pose(rig,base,phase,action)
    return rig


def make_clip(base,source_sha,action='walk',count=8,fps=8):
    if count not in (8,16) or not 1<=fps<=30: raise ValueError('动作支持 8 / 16 帧，帧率 1–30。')
    base=with_feet(base)
    frames=[pose_at(base,i/(count-1 if action in ONE_SHOT_ACTIONS else count),action) for i in range(count)]
    clip={'schema_version':1,'source_sha256':source_sha,'action':action,'frame_count':count,'fps':fps,
          'canvas':[768,1024],'base_rig':base,'frames':frames,'edited':False,'loop':action not in ONE_SHOT_ACTIONS,'generator_version':3}
    validate_clip(clip); return clip


def validate_clip(clip):
    if clip.get('schema_version')!=1 or clip.get('action') not in ACTIONS: raise ValueError('无效的动作文件。')
    if clip.get('frame_count') not in (8,16) or len(clip.get('frames',[]))!=clip['frame_count']:
        raise ValueError('骨骼帧数量不完整。')
    for rig in [clip['base_rig']]+clip['frames']:
        for name in JOINT_NAMES+list(FOOT_NAMES):
            value=rig['joints'].get(name)
            if not value or len(value)!=3 or not all(math.isfinite(float(n)) for n in value): raise ValueError('骨骼关节无效：'+name)
            if not -64<=value[0]<=832 or not -64<=value[1]<=1088: raise ValueError('关节超出画布：'+JOINT_LABELS[name])
    return clip


def sample_clip(clip,phase):
    if not clip.get('edited') and clip.get('generator_version',2)>=3:
        return pose_at(clip['base_rig'],phase,clip['action'])
    n=len(clip['frames'])
    if not clip.get('loop',True):
        at=max(0.,min(1.,phase))*(n-1); left=min(int(at),n-1); right=min(left+1,n-1)
    else:
        at=(phase%1)*n; left=int(at)%n; right=(left+1)%n
    f=at-math.floor(at)
    rig=deepcopy(clip['frames'][left])
    for name,p in rig['joints'].items():
        q=clip['frames'][right]['joints'][name]
        rig['joints'][name]=[p[k]*(1-f)+q[k]*f for k in range(3)]
    rig['phase']=phase; return rig


def body_pose(rig,base=None):
    """Convert foot controls to the standard ankle endpoint expected by BODY_18 models."""
    result=deepcopy(rig)
    if base:
        for side in ('right','left'):
            source=base['joints']; p=rig['joints']
            a,b=source[side+'_heel'],source[side+'_toe']; heel,toe=p[side+'_heel'],p[side+'_toe']
            angle=math.atan2(toe[1]-heel[1],toe[0]-heel[0])-math.atan2(b[1]-a[1],b[0]-a[0])
            dx=source[side+'_ankle'][0]-(a[0]+b[0])/2; dy=source[side+'_ankle'][1]-(a[1]+b[1])/2
            result['joints'][side+'_ankle']=[(heel[0]+toe[0])/2+dx*math.cos(angle)-dy*math.sin(angle),
                (heel[1]+toe[1])/2+dx*math.sin(angle)+dy*math.cos(angle),1]
    return result


def paint_rig(rig,size=(480,640),background=None,include_feet=True):
    image=Image.new('RGB',(768,1024),'black')
    if background:
        with Image.open(background) as source: image=source.convert('RGB').resize((768,1024))
    draw=ImageDraw.Draw(image); p=rig['joints']
    for i,(a,b) in enumerate(LIMBS):
        pa,pb=p[JOINT_NAMES[a]],p[JOINT_NAMES[b]]
        draw.line((*pa[:2],*pb[:2]),fill=COLORS[i%len(COLORS)],width=5)
    if include_feet:
        for side,color in (('right','#ffb000'),('left','#00d4ff')):
            draw.line([tuple(p[side+'_ankle'][:2]),tuple(p[side+'_heel'][:2]),tuple(p[side+'_toe'][:2])],fill=color,width=5)
    points=list(p.values()) if include_feet else [p[name] for name in JOINT_NAMES]
    for i,point in enumerate(points):
        x,y=point[:2]; draw.ellipse((x-5,y-5,x+5,y+5),fill=COLORS[i%len(COLORS)])
    return image.resize(size,Image.Resampling.LANCZOS)


def save_clip(clip,path=None):
    validate_clip(clip); path=Path(path) if path else clip_path(clip['source_sha256'],clip['action'])
    write_json(path,clip); return path
