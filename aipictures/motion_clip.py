"""Character-sized biped motion clips. Complete cycles, named joints and editable feet."""
import math
from copy import deepcopy
from pathlib import Path

from PIL import Image,ImageDraw

from .character_profile import JOINT_NAMES,LIMBS,COLORS
from .storage import DATA,write_json
from .walk_cycle import walk_rig,knee_ik
from .animation_actions import ACTIONS,stage_label
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


def feet_for_pose(rig,base,phase,action):
    p=rig['joints']; source=base['joints']
    for side,offset in (('right',0),('left',.5)):
        ankle=p[side+'_ankle']; original=source[side+'_ankle']
        # Each ankle owns exactly one heel and one toe; never duplicate an entire shoe pair.
        angle=0
        if action in ('walk','run'):
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
    phase=phase%1
    base=with_feet(base); t=phase*math.tau
    if action=='walk':
        rig=walk_rig(phase,'normal',base)
    elif action=='run':
        rig=deepcopy(base); p=rig['joints']; source=base['joints']
        leg_length=math.dist(source['right_hip'][:2],source['right_knee'][:2])+math.dist(source['right_knee'][:2],source['right_ankle'][:2])
        lift=min(55,leg_length*.13)*max(0,math.sin(t*2))
        drop=max(0,source['right_ankle'][1]-source['right_hip'][1]-.86*leg_length)
        for point in p.values(): point[1]+=drop-lift
        for side,offset in (('right',0),('left',math.pi)):
            q=t+offset; hip=p[side+'_hip']
            ankle=[hip[0]+leg_length*.28*math.cos(q),source[side+'_ankle'][1]-lift-leg_length*.28*max(0,-math.sin(q)),1]
            upper=math.dist(source[side+'_hip'][:2],source[side+'_knee'][:2]); lower=math.dist(source[side+'_knee'][:2],source[side+'_ankle'][:2])
            dx,dy=ankle[0]-hip[0],ankle[1]-hip[1]; distance=math.hypot(dx,dy)
            target=max(abs(upper-lower)+.001,min(upper+lower-.001,distance))
            ankle[:2]=[hip[0]+dx*target/distance,hip[1]+dy*target/distance]
            p[side+'_ankle']=ankle; p[side+'_knee']=knee_ik(hip,ankle,upper,lower)
            shoulder=p[side+'_shoulder']; elbow=p[side+'_elbow']; wrist=p[side+'_wrist']
            upper=math.dist(source[side+'_shoulder'][:2],source[side+'_elbow'][:2]); lower=math.dist(source[side+'_elbow'][:2],source[side+'_wrist'][:2])
            angle=-.55*math.cos(q)
            elbow[:2]=[shoulder[0]+upper*math.sin(angle),shoulder[1]+upper*math.cos(angle)]
            wrist[:2]=[elbow[0]+lower*math.sin(angle+1.3),elbow[1]+lower*math.cos(angle+1.3)]
    else:
        rig=deepcopy(base); p=rig['joints']
        if action=='idle':
            for name,point in p.items():
                if 'ankle' not in name and name not in FOOT_NAMES: point[1]+=2*math.sin(t)
        elif action=='reach':
            amount=(1-math.cos(t))/2
            for side,factor in (('right',1),('left',.1)):
                shoulder=p[side+'_shoulder']; elbow=p[side+'_elbow']; wrist=p[side+'_wrist']
                upper=math.dist(shoulder[:2],elbow[:2]); lower=math.dist(elbow[:2],wrist[:2])
                angle=amount*math.pi/2*factor
                elbow[:2]=[shoulder[0]+upper*math.sin(angle),shoulder[1]+upper*math.cos(angle)]
                wrist[:2]=[elbow[0]+lower*math.sin(angle),elbow[1]+lower*math.cos(angle)]
        elif action=='jump':
            # Crouch -> airborne -> landing -> rest; root motion is retained on export.
            keys=((0,0),(.12,30),(.22,0),(.48,-60),(.72,0),(.84,24),(1,0))
            shift=0
            for (a,ya),(b,yb) in zip(keys,keys[1:]):
                if a<=phase<=b:
                    f=(1-math.cos(math.pi*(phase-a)/(b-a)))/2; shift=ya+(yb-ya)*f; break
            up=max(0,math.sin(math.pi*(phase-.22)/.5)) if .22<phase<.72 else 0
            for point in p.values(): point[1]+=shift
            for side in ('right','left'):
                hip=p[side+'_hip']; source=base['joints']
                ankle=source[side+'_ankle'][:]
                if up>0: ankle[1]+=shift-20*up
                upper=math.dist(source[side+'_hip'][:2],source[side+'_knee'][:2])
                lower=math.dist(source[side+'_knee'][:2],source[side+'_ankle'][:2])
                p[side+'_ankle']=ankle; p[side+'_knee']=knee_ik(hip,ankle,upper,lower)
                shoulder=p[side+'_shoulder']; elbow=p[side+'_elbow']; wrist=p[side+'_wrist']
                upper=math.dist(shoulder[:2],elbow[:2]); lower=math.dist(elbow[:2],wrist[:2]); angle=up*math.pi*.65
                elbow[:2]=[shoulder[0]+upper*math.sin(angle),shoulder[1]+upper*math.cos(angle)]
                wrist[:2]=[elbow[0]+lower*math.sin(angle),elbow[1]+lower*math.cos(angle)]
    enrich_body(rig,base,phase,action)
    rig.update(action=action,phase=phase,stage=stage_label(action,phase),ground_y=base.get('ground_y',978))
    feet_for_pose(rig,base,phase,action)
    return rig


def make_clip(base,source_sha,action='walk',count=8,fps=8):
    if count not in (8,16) or not 1<=fps<=30: raise ValueError('动作支持 8 / 16 帧，帧率 1–30。')
    base=with_feet(base)
    frames=[pose_at(base,i/count,action) for i in range(count)]
    clip={'schema_version':1,'source_sha256':source_sha,'action':action,'frame_count':count,'fps':fps,
          'canvas':[768,1024],'base_rig':base,'frames':frames,'edited':False,'loop':action!='jump','generator_version':2}
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
    if not clip.get('edited'): return pose_at(clip['base_rig'],phase,clip['action'])
    n=len(clip['frames']); at=(phase%1)*n; left=int(at)%n; right=(left+1)%n; f=at-math.floor(at)
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
