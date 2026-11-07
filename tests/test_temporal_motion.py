import json
import threading
from pathlib import Path

import pytest
from PIL import Image,ImageDraw

from aipictures.intent_media import prepare
from aipictures.temporal_motion import observe_motion,describe_change


class Session:
    def __init__(self,*args):self.calls=0
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def complete(self,messages,**kwargs):
        schema=kwargs.get('schema')
        if schema and 'facing' in schema['properties']:
            self.calls+=1;n=schema['properties']['facing']['minItems']
            return json.dumps(dict(facing=['front']*n,left_arm=['head' if i%2 else 'down' for i in range(n)],
                right_arm=['waist']*n,feet=['both_down']*n,body=['upright']*n,camera='fixed',uncertainties='')),{}
        return json.dumps(dict(kind='animation',summary='跟随原动作',positive_prompt='目标跟随参考动作。',
            negative_prompt='身份突变',observations=[],timeline=[],questions=[])),{}


def source(tmp_path:Path,count=70):
    frames=[Image.new('RGB',(32,48),(i*3%255,i*13%255,50)) for i in range(count)]
    path=tmp_path/'source.gif';frames[0].save(path,save_all=True,append_images=frames[1:],duration=40,loop=0)
    return path


def test_archived_dense_observer_still_covers_source(tmp_path):
    # Historical utility only: the application no longer calls this observer.
    clip=source(tmp_path);original=clip.read_bytes()
    folder=tmp_path/'analysis'
    _,evidence=prepare(None,clip,folder,threading.Event(),max_frames=64,seconds=30)
    asset=evidence['assets'][0];session=Session()
    assert len(asset['frames'])==64
    result=observe_motion(session,asset,folder,{},'')
    rows=result['target_timeline']
    assert rows[0]['start']==0 and rows[-1]['end']==pytest.approx(2.8)
    assert all(a['end']==b['start'] for a,b in zip(rows,rows[1:]))
    assert len(rows)>8 and session.calls>0
    assert clip.read_bytes()==original


def test_bounded_windows_share_endpoint_and_preserve_irregular_pts(tmp_path):
    clip=source(tmp_path,11);folder=tmp_path/'observed'
    _,evidence=prepare(None,clip,folder,threading.Event(),max_frames=64,seconds=30)
    asset=evidence['assets'][0];session=Session()
    # Deliberately irregular timestamps; model is never allowed to emit replacements.
    for i,row in enumerate(asset['frames']):row['time']=i*i*.003
    asset['end']=.44
    result=observe_motion(session,asset,folder,{},'')
    assert session.calls==2 and len(result['frames'])==11
    assert [r['time'] for r in result['frames']]==[r['time'] for r in asset['frames']]
    assert result['target_timeline'][-1]['end']==.44


def test_motion_changes_are_not_silently_labelled_static(tmp_path):
    clip=source(tmp_path,3);folder=tmp_path/'out'
    _,evidence=prepare(None,clip,folder,threading.Event(),max_frames=64)
    class Unresolved(Session):
        def complete(self,*args,**kwargs):
            text,stats=super().complete(*args,**kwargs);v=json.loads(text);v['left_arm']=['down']*len(v['left_arm'])
            return json.dumps(v),stats
    result=observe_motion(Unresolved(),evidence['assets'][0],folder,{},'')
    assert result['review_intervals'] and '待核对' in result['target_timeline'][0]['description']
    assert '静止' not in result['target_timeline'][0]['description']


def test_invalid_frame_state_fails_before_timeline_application(tmp_path):
    clip=source(tmp_path,3);folder=tmp_path/'out'
    _,evidence=prepare(None,clip,folder,threading.Event(),max_frames=64)
    class Bad(Session):
        def complete(self,*args,**kwargs):
            text,stats=super().complete(*args,**kwargs);v=json.loads(text);v['feet'][0]={}
            return json.dumps(v),stats
    with pytest.raises(ValueError,match='帧数或状态'):
        observe_motion(Bad(),evidence['assets'][0],folder,{},'')


def test_last_visible_frame_can_be_held_without_inventing_next_action(tmp_path):
    clip=source(tmp_path,3);folder=tmp_path/'out'
    _,evidence=prepare(None,clip,folder,threading.Event(),max_frames=64,start=.08,seconds=.04)
    result=observe_motion(Session(),evidence['assets'][0],folder,{},'')
    assert len(result['frames'])==1 and result['target_timeline'][0]['end']==pytest.approx(.12)
    assert result['target_timeline'][0]['description'].startswith('保持最后可见姿势')


def test_front_facing_arm_movement_is_not_a_turn():
    a=dict(facing='front',left_arm='down',right_arm='chest',feet='both_down',body='upright')
    b=dict(a,left_arm='head')
    text=describe_change(a,b,True)
    assert '移至头部' in text and '转向' not in text and '转身' not in text


def test_foot_height_evidence_requires_isolated_visible_components(tmp_path):
    from aipictures.foot_evidence import foot_heights
    image=Image.new('RGB',(100,100),(210,210,210));draw=ImageDraw.Draw(image)
    draw.rectangle((35,5,65,65),fill='blue')
    draw.rectangle((35,85,45,93),fill='black');draw.rectangle((55,87,65,97),fill='black')
    path=tmp_path/'feet.png';image.save(path)
    result=foot_heights(path)
    assert result and result['state']=='left_up' and result['left_bottom']<result['right_bottom']
    draw.rectangle((35,80,45,99),fill=(210,210,210));image.save(path)
    assert foot_heights(path) is None,'An occluded or missing foot must not be invented.'


def test_visual_grounding_uses_model_recommended_minimum_token_budget(tmp_path):
    from aipictures.local_intent import LocalSession
    session=LocalSession(dict(server='server',model='model',projector='projector',context=8192),tmp_path,threading.Event(),lambda *_:None)
    command=session.command(1234)
    assert command[command.index('--image-min-tokens')+1]=='1024'
