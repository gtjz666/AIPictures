"""Continuation uses independent source frames; interrupted parts are explicitly resumable."""
import json
import math
import threading
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from aipictures.video_chain import plan,generate,segment_params
from aipictures.video_io import preview_frames
from aipictures.workflow_library import digest
from aipictures.engine import Cancelled


@pytest.mark.parametrize('seconds',[8.001,15,16,17.3,31,60,7200])
def test_balanced_plan_covers_output_clock_and_stays_inside_validated_clip_budget(seconds):
    parts=plan(seconds)
    assert parts[0]['start']==0 and sum(p['frames'] for p in parts)==math.ceil(seconds*24)
    assert parts[-1]['end']==math.ceil(seconds*24)/24
    for i,p in enumerate(parts):
        assert p['frames']>=48
        frames=p['frames']+(i>0);aligned=frames+(5-frames)%17
        assert aligned<=192
        if i:assert parts[i-1]['end']==p['start']


def test_segment_uses_next_source_interval_and_clips_editable_actions(tmp_path):
    params=dict(prompt='保持外观',seed=12,seconds=20,motion_reference='motion.gif',motion_start=1.,motion_repeat=False,
        motion_source={'duration':30},motion_timeline=[dict(start=5,end=10,description='抬手')])
    part=dict(index=1,start=8,end=14,frames=144)
    result=segment_params(params,part,tmp_path/'last.png')
    assert result['motion_start']==pytest.approx(9-1/24) and result['seed']==13
    assert '0.042–2.042秒：抬手' in result['prompt']
    source=dict(params,motion_timeline_clock='source',motion_timeline=[dict(start=9,end=10,description='抬手')])
    assert '0.042–1.042秒：抬手' in segment_params(source,part,tmp_path/'last.png')['prompt']
    params['motion_repeat']=True;params['motion_source']['duration']=2
    assert segment_params(params,part,tmp_path/'last.png')['motion_start']==pytest.approx((9-1/24)%2)


def fake_backend(folder,params,cancel,emit):
    paths=[]
    if params.get('continuation_frame'):
        with Image.open(params['continuation_frame']) as im:base=np.asarray(im.convert('RGB'))[0,0,0]
    else:base=0
    count=math.ceil(params['seconds']*24);count+=(5-count)%17
    for i in range(count):
        p=folder/f'{i:04d}.png';Image.new('RGB',(16,24),(int(base)+i,40,90)).save(p);paths.append(str(p))
    return dict(video=str(folder/'unused.mp4'),native_frames=paths)


def test_long_animation_resume_and_lossless_master_roundtrip(tmp_path):
    params=dict(engine='h3',prompt='抬手再收回',negative='',seed=8,seconds=17,prompt_layout='unified')
    calls=[]
    def interrupted(folder,p,cancel,emit):
        calls.append(folder)
        if len(calls)==2:raise ValueError('interrupted')
        return fake_backend(folder,p,cancel,emit)
    with patch('aipictures.h3_backend.generate',side_effect=interrupted):
        with pytest.raises(ValueError,match='interrupted'):generate(tmp_path,params,threading.Event(),lambda *_:None)
    state=json.loads((tmp_path/'chain.json').read_text('utf-8'))
    first=state['parts'][0];before=first['sha256']
    with patch('aipictures.h3_backend.generate',side_effect=fake_backend) as backend:
        with pytest.raises(ValueError,match='选择继续'):generate(tmp_path,params,threading.Event(),lambda *_:None)
        result=generate(tmp_path,dict(params,resume_chain=True),threading.Event(),lambda *_:None)
        assert backend.call_count==len(plan(17))-1
    assert [digest(tmp_path/p) for p in first['frames']]==before
    final=json.loads((tmp_path/'chain.json').read_text('utf-8'))
    assert final['parts'][1]['attempt']==2 and final['status']=='completed' and not final['temporal_blending']
    assert len(result['native_frames'])==408
    decoded,fps=preview_frames(Path(result['video']),tmp_path/'decoded',threading.Event(),lambda *_:None)
    for a,b in zip(result['native_frames'],decoded):
        with Image.open(a) as x,Image.open(b) as y:assert x.convert('RGB').tobytes()==y.convert('RGB').tobytes()
    with pytest.raises(ValueError,match='参数或素材不一致'):
        generate(tmp_path,dict(params,seed=9,resume_chain=True),threading.Event(),lambda *_:None)


def test_cancel_keeps_completed_parts_and_does_not_start_another(tmp_path):
    cancel=threading.Event();params=dict(prompt='动作',seed=1,seconds=18)
    def stop(folder,p,c,emit):
        result=fake_backend(folder,p,c,emit);cancel.set();return result
    with patch('aipictures.h3_backend.generate',side_effect=stop) as backend:
        with pytest.raises(Cancelled):generate(tmp_path,params,cancel,lambda *_:None)
        assert backend.call_count==1
    state=json.loads((tmp_path/'chain.json').read_text('utf-8'))
    assert state['status']=='cancelled' and state['parts'][0]['status']=='completed'


def test_native_continuation_uses_official_guide_without_replacing_reference_conditioning():
    from aipictures.motion_native_graph import anchor_continuation
    graph={'checkpoint':{'inputs':{'conditioning':['references',0],'latent':['references',1]}}}
    anchor_continuation(graph,{'MiniMaxH3AddGuide':{}},'last.png')
    assert graph['anchor']['inputs']['positive']==['references',0]
    assert graph['anchor']['inputs']['frame_idx']==0 and graph['checkpoint']['inputs']['conditioning']==['anchor',0]
    assert graph['checkpoint']['inputs']['latent']==['references',1]


def test_live_chain_lock_prevents_duplicate_resume(tmp_path):
    from aipictures.video_chain import job_lock
    with job_lock(tmp_path):
        with pytest.raises(ValueError,match='其他窗口'):
            with job_lock(tmp_path):pass
    with job_lock(tmp_path):pass


def test_non_looping_reference_can_hold_last_pose_in_later_segments(tmp_path):
    from aipictures.motion_guide import prepare
    images=[Image.new('RGB',(16,24),(i*80,20,40)) for i in range(3)]
    source=tmp_path/'motion.gif';images[0].save(source,save_all=True,append_images=images[1:],duration=100)
    result=prepare(source,tmp_path/'guide',2,4,threading.Event(),align_h3=True,allow_tail_hold=True,
                   encode_video=False,save_frames=True,max_side=256)
    assert result['frames']>=22 and not result['temporal_blending']
    frame=json.loads(Path(result['path']).read_text('utf-8'))['frames'][-1]
    with Image.open(Path(result['path']).parent/frame['image']) as last:assert last.convert('RGB').getpixel((0,0))==(160,20,40)


def test_complete_long_manifest_can_preview_and_export_beyond_old_480_frame_cap(tmp_path):
    from aipictures.video_generation import generate as pipeline
    from aipictures.selected_frames import read_source,export_selection
    with patch('aipictures.h3_backend.generate',side_effect=fake_backend):
        result=pipeline(None,tmp_path/'job',dict(engine='h3',prompt='动作',negative='',seed=1,seconds=21),threading.Event(),lambda *_:None)
    data,frames=read_source(Path(result['manifest']))
    assert len(frames)==504 and data['duration_seconds']==21 and data['native_rgb_preserved']
    indices=[0,250,503]
    (tmp_path/'exported').mkdir()
    exported=export_selection(Path(result['manifest']),indices,tmp_path/'selection',tmp_path/'exported','pngs',24,3,
        False,True,threading.Event(),lambda *_:None)
    manifest=json.loads(Path(exported['manifest']).read_text('utf-8'))
    assert manifest['source_indices']==indices
    for i,index in enumerate(indices):
        with Image.open(tmp_path/'selection'/f'frame_{i:03d}.png') as chosen,Image.open(frames[index]) as original:
            assert chosen.convert('RGB').tobytes()==original.convert('RGB').tobytes()
