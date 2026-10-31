"""Explicit local action sequencing. Unknown instructions never silently become walking."""
import math
import re
from copy import deepcopy

from .animation_actions import PRESET_ACTIONS, ONE_SHOT_ACTIONS

WORDS={
    'walk':('走路','行走','步行','walk','walking'),
    'idle':('待机','站立','休息','idle','stand'),
    'run':('跑步','奔跑','run','running'),
    'jump':('横版跳跃','跳跃','起跳','跳起来','jump','jumping'),
    'squat':('下蹲','蹲下','深蹲','squat','crouch'),
    'attack':('基础攻击','攻击','出拳','挥拳','打拳','attack','punch'),
}
TOKEN=re.compile('|'.join(sorted((re.escape(w) for words in WORDS.values() for w in words),key=len,reverse=True)),re.I)


def parse_plan(description: str) -> dict:
    """Parse ordered primitives with optional seconds; the UI exposes unsupported text."""
    text=description.strip()
    if not text:raise ValueError('请填写动作说明，例如：下蹲1秒，然后出拳1秒。')
    if re.search(r'不要|禁止|不能|别|not\b|without\b',text,re.I):
        raise ValueError('骨骼编排只接受要执行的动作；排除内容请填入反向提示词。')
    matches=list(TOKEN.finditer(text));segments=[]
    remainder=TOKEN.sub(' ',text)
    remainder=re.sub(r'\d+(?:\.\d+)?\s*(?:秒|seconds?|s\b)',' ',remainder,flags=re.I)
    remainder=re.sub(r'然后|接着|最后|之后|先|再|正常|一次|原地|向前|的|动作|请|角色|人物|动画|执行|then', ' ',remainder,flags=re.I)
    remainder=re.sub(r'[\s，,。.;；、→+]+','',remainder)
    if remainder or not matches:
        raise ValueError('骨骼编排暂不支持：'+(remainder or text)+'。可选走路、待机、跑步、跳跃、下蹲、出拳及组合；其他动作请选择“AI 自由动作”。')
    for i,match in enumerate(matches):
        action=next(a for a,words in WORDS.items() if match.group().lower() in words)
        suffix=text[match.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        duration=re.search(r'(\d+(?:\.\d+)?)\s*(?:秒|seconds?|s\b)',suffix,re.I)
        seconds=float(duration[1]) if duration else 1.
        if not .2<=seconds<=10:raise ValueError('每段动作时长应在 0.2–10 秒之间。')
        segments.append({'action':action,'seconds':seconds,'title':PRESET_ACTIONS[action][0]})
    if len(segments)>6:raise ValueError('一次最多编排 6 段动作，请拆分生成。')
    return {'version':1,'description':text,'segments':segments,'duration_seconds':sum(s['seconds'] for s in segments)}


def _blend_rest(pose,base,weight):
    """Blend joint angles, preserving limb lengths rather than interpolating their endpoints."""
    from .motion_clip import feet_for_pose
    from .motion_kinematics import smooth
    weight=smooth(weight);result=deepcopy(pose);p=result['joints'];source=base['joints'];target=pose['joints']
    for name,point in p.items():point[:2]=[source[name][i]*(1-weight)+point[i]*weight for i in (0,1)]
    for side in ('right','left'):
        for a,b in (('hip','knee'),('knee','ankle'),('shoulder','elbow'),('elbow','wrist')):
            a,b=side+'_'+a,side+'_'+b
            angle0=math.atan2(source[b][1]-source[a][1],source[b][0]-source[a][0])
            angle1=math.atan2(target[b][1]-target[a][1],target[b][0]-target[a][0])
            angle=angle0+math.atan2(math.sin(angle1-angle0),math.cos(angle1-angle0))*weight
            length=math.dist(source[a][:2],source[b][:2])
            p[b][:2]=[p[a][0]+length*math.cos(angle),p[a][1]+length*math.sin(angle)]
    result['contacts']={'right':False,'left':False}
    return feet_for_pose(result,base,pose['phase'],pose['action'])


def sample_plan(base,plan,phase):
    from .motion_clip import pose_at,with_feet
    base=with_feet(base);phase=max(0.,min(1.,phase));at=phase*plan['duration_seconds'];cursor=0.
    for index,segment in enumerate(plan['segments']):
        end=cursor+segment['seconds']
        if at<=end or index==len(plan['segments'])-1:
            local=max(0.,min(1.,(at-cursor)/segment['seconds']));action=segment['action']
            pose=pose_at(base,local,action)
            if action not in ONE_SHOT_ACTIONS:
                pose=_blend_rest(pose,base,min(1.,local/.12,(1-local)/.12))
            if local<=0 or local>=1:pose['joints']=deepcopy(base['joints'])
            pose.update(action='custom',phase=phase,segment=index,
                        stage=f'{index+1}/{len(plan["segments"])} · {segment["title"]} · '+pose['stage'])
            return pose
        cursor=end


def make_custom_clip(base,source_sha,description,count=16,fps=8):
    from .motion_clip import with_feet,validate_clip
    if count not in (8,16) or not 1<=fps<=30:raise ValueError('动作支持 8 / 16 帧，帧率 1–30。')
    plan=parse_plan(description);base=with_feet(base)
    clip={'schema_version':1,'source_sha256':source_sha,'action':'custom','frame_count':count,'fps':fps,
          'canvas':[768,1024],'base_rig':base,'frames':[sample_plan(base,plan,i/(count-1)) for i in range(count)],
          'edited':False,'loop':False,'generator_version':4,'motion_plan':plan}
    return validate_clip(clip)


def rebuild_clip(clip,base=None):
    from .motion_clip import make_clip
    args=(base or clip['base_rig'],clip['source_sha256'])
    if clip['action']=='custom':return make_custom_clip(*args,clip['motion_plan']['description'],clip['frame_count'],clip['fps'])
    return make_clip(*args,clip['action'],clip['frame_count'],clip['fps'])
