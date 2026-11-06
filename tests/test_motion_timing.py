"""The prompt clock follows actual source selection, including wraps and held tails."""
import json
import threading
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from PIL import Image
from aipictures.motion_timing import source_to_output
from aipictures.motion_guide import prepare


ROWS=[dict(start=i,end=i+1,description=str(i)) for i in range(3)]


@pytest.mark.parametrize('repeat',[False,True])
def test_output_timeline_matches_actual_guide_pixels(tmp_path,repeat):
    frames=[Image.new('RGB',(16,24),(i*80,20,40)) for i in range(3)]
    source=tmp_path/'source.gif'
    frames[0].save(source,save_all=True,append_images=frames[1:],duration=1000)
    guide=prepare(source,tmp_path/'guide',4,1.5,threading.Event(),max_side=256,repeat=repeat,
                  align_h3=True,allow_tail_hold=True,encode_video=False,save_frames=True)
    rows=source_to_output(ROWS,3.,4.,start=1.5,repeat=repeat)
    data=json.loads(Path(guide['path']).read_text('utf-8'))
    assert len(data['frames'])>=96
    for i,row in enumerate(data['frames'][:96]):
        t=i/24
        action=next(r['description'] for r in rows if r['start']<=t<r['end'])
        expected=2 if action=='保持参考末帧可见姿势' else int(action)
        with Image.open(Path(guide['path']).parent/row['image']) as image:
            assert image.convert('RGB').getpixel((0,0))==(expected*80,20,40)
    assert rows[0]['start']==0 and rows[-1]['end']==4


def test_long_source_is_clipped_without_speed_change():
    rows=source_to_output(ROWS+[dict(start=3,end=9.3,description='后续动作')],9.3,2,start=.5,repeat=True)
    assert rows==[dict(start=0.,end=.5,description='0'),dict(start=.5,end=1.5,description='1'),
                  dict(start=1.5,end=2.,description='2')]


def test_prompt_organizer_uses_direct_guide_without_observing_complex_gif(tmp_path):
    from aipictures.local_intent import analyze
    class Session:
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def complete(self,messages,**kwargs):
            assert '不分析其中的动作' in messages[1]['content'][-1]['text']
            assert json.loads(messages[1]['content'][0]['text'])['motion_reference_priority']=='video_first'
            assert not any(item['type']=='image_url' for item in messages[1]['content'])
            return json.dumps(dict(kind='animation',summary='替换角色',positive_prompt='蓝色机器人',
                negative_prompt='身份突变',timeline=[],observations=[],questions=[])),{}
    gif=tmp_path/'complex.gif';gif.write_bytes(b'opaque-motion-fixture')
    with patch('aipictures.intent_observation.observe') as observe:
        result=analyze({},'替换参考动画中的角色','',None,gif,tmp_path/'job',threading.Event(),
                       selected_kind='animation',describe_motion=False,session_factory=Session)
        observe.assert_not_called()
    assert result['route']=='h3_reference' and not result['plan']['timeline']
    assert '实际动作参考为准' in result['plan']['positive_prompt']
    assert result['evidence']['assets'][0]['source']==str(gif)


def test_direct_motion_with_appearance_does_not_send_unobserved_gif_to_observer(tmp_path):
    from aipictures.local_intent import analyze
    reference=tmp_path/'character.png';Image.new('RGB',(24,32),'blue').save(reference)
    gif=tmp_path/'complex.gif';gif.write_bytes(b'not-decoded-in-this-route')
    class Session:
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def complete(self,messages,**kwargs):
            return json.dumps(dict(kind='animation',summary='角色替换',positive_prompt='蓝色机器人',
                negative_prompt='身份突变',timeline=[],observations=[],questions=[])),{}
    def observe(session,content,evidence,*args,**kwargs):
        assert [a['id'] for a in evidence['assets']]==['appearance']
        return dict(appearance=dict(identity='蓝色机器人',reference_use='appearance'))
    with patch('aipictures.intent_observation.observe',side_effect=observe), \
         patch('aipictures.intent_quality.repair_anatomy',side_effect=lambda session,raw,*a:raw):
        result=analyze({},'替换为蓝色机器人','',reference,gif,tmp_path/'job',threading.Event(),
                       selected_kind='animation',describe_motion=False,session_factory=Session)
    assert result['route']=='h3_reference' and not result['plan']['timeline']
    assert result['resolved_reference_role']=='appearance'


def test_detailed_analysis_keeps_uncertain_motion_out_of_prompt_planning(tmp_path):
    from aipictures.local_intent import analyze
    gif=tmp_path/'source.gif'
    Image.new('RGB',(16,24),'red').save(gif,save_all=True,
        append_images=[Image.new('RGB',(16,24),'blue')],duration=[1000,1000])
    timeline=[dict(start=0,end=1,description='猜测动作一'),dict(start=1,end=2,description='猜测动作二')]
    observations=dict(motion=dict(target_timeline=timeline,
        frames=[dict(time=0,pose='猜测动作一'),dict(time=1,pose='猜测动作二')],
        camera='猜测固定全身构图',summaries=['猜测动作一'],uncertainties='待核对',method='test'))
    class Session:
        calls=0
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def complete(self,messages,**kwargs):
            Session.calls+=1
            details=json.loads(messages[1]['content'][0]['text'])
            assert details['motion_reference_priority']=='video_first'
            assert '猜测' not in json.dumps(details,ensure_ascii=False)
            assert '不能将分析中的动作' in messages[1]['content'][-1]['text']
            return json.dumps(dict(kind='animation',summary='角色替换',positive_prompt='蓝色机器人',
                negative_prompt='身份突变',timeline=[],observations=[],questions=[])),{}
    with patch('aipictures.intent_observation.observe',return_value=observations):
        result=analyze({},'蓝色机器人模仿参考','用户原有排除项',None,gif,tmp_path/'job',threading.Event(),
            selected_kind='animation',seconds=2,output_seconds=2,describe_motion=True,session_factory=Session)
    assert Session.calls==1 and result['plan']['timeline']==timeline
    assert '实际动作参考为准' in result['plan']['positive_prompt']
    assert '猜测' not in result['plan']['positive_prompt']
    assert '用户原有排除项' in result['plan']['negative_prompt']
    assert result['engine_released'] and result['route']=='h3_reference'
