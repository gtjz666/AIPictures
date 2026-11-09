import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from aipictures.multi_reference import analyze, bind_text, build, clean_generated_prompt
from aipictures.workflow import ImageRequest
from tests.test_image_choice_retirement import model_info


def test_label_binding_survives_gaps_and_rejects_missing_images():
    assert bind_text('图二的人物，图4的风格；Image 2的衣服', [2,4]) == 'Image 1的人物，Image 2的风格；Image 1的衣服'
    with pytest.raises(ValueError, match='图1'):bind_text('图1的人物', [2,4])
    with pytest.raises(ValueError, match='图5'):bind_text('图五', [1,2,3,4])


def test_generated_meta_instructions_do_not_become_visual_constraints():
    assert clean_generated_prompt('Use 图1. No questions needed. No additional restrictions or negative prompts are added.')=='Use 图1.'
    assert clean_generated_prompt('no collage, no text, no motion or time-based elements.')=='no collage, no text.'


def test_all_images_are_independent_ordered_conditions_with_fresh_output_latent():
    info=model_info();info['AIPicturesReleaseCompletedEncoders']={}
    request=ImageRequest('unused','图2人物、图4画风',seed=32)
    graph, mapping=build(request,info,{2:'character.png',4:'style.png'})
    assert graph['image_2']['inputs']['image']=='character.png'
    assert graph['image_4']['inputs']['image']=='style.png'
    assert graph['pos_image_4']['inputs']['conditioning']==['pos_image_2',0]
    assert graph['release']['inputs']['conditioning']==['pos_image_4',0]
    assert graph['guider']['inputs']['positive']==['pos_image_4',0]
    assert graph['sample']['inputs']['latent_image']==['latent',0]
    assert graph['latent']['class_type']=='EmptyFlux2LatentImage'
    assert mapping['numbered_references']=={'2':'image_2','4':'image_4'}
    assert 'Image 1人物、Image 2画风' in graph['text']['inputs']['text']
    with pytest.raises(ValueError):build(replace(request,positive='图3'),info,{2:'a'})


def test_ground_each_picture_separately_then_plan_without_mixed_visual_roles(tmp_path):
    references={}
    for i in (1,2,4):
        p=tmp_path/f'{i}.png';Image.new('RGB',(20,30),(i*30,50,120)).save(p);references[i]=p
    calls=[];closed=[]
    class Session:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):closed.append(True)
        def complete(self,messages,**kwargs):
            calls.append(messages)
            if len(calls)<=3:return json.dumps(dict(subject='人物',appearance='服装',style='画法',pose_composition='举手',uncertain='')),{}
            if len(calls)==4:
                return json.dumps(dict(summary='保留图1人物，图2姿势，图4画风',positive_prompt='采用图1的人物、图2的姿势和图4的画风。',negative_prompt='不要文字',render_order=[2,1,4],questions=[])),{}
            return json.dumps(dict(positive_prompt='Use the person from Image 1, the pose from Image 2 and the style from Image 4.',
                negative_prompt='No text')),{}
    result=analyze({},'图1人物，图2姿势，图4画风','不要文字',references,tmp_path/'run',threading.Event(),lambda *a:None,session_factory=Session)
    assert closed and len(calls)==5
    for call in calls[:3]:assert sum(v.get('type')=='image_url' for v in call[1]['content'])==1
    assert isinstance(calls[3][1]['content'],str) and isinstance(calls[4][1]['content'],str)
    assert result['plan']['timeline']==[] and result['plan']['negative_prompt']=='不要文字'
    assert result['english']['positive'].startswith('Use the person from Image 1') and result['english']['negative']=='No text'
    assert sum(v.get('type')=='image_url' for call in calls[3:] for v in (call[1]['content'] if isinstance(call[1]['content'],list) else []))==0
    assert [v['number'] for v in result['assets']]==[1,2,4]
    with pytest.raises(ValueError,match='图3'):
        analyze({},'使用图3','',references,tmp_path/'bad',threading.Event(),lambda *a:None,session_factory=Session)
    assert not (tmp_path/'bad').exists()
