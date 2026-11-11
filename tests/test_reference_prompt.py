import json
import threading
from unittest.mock import Mock
import pytest
from PIL import Image
from aipictures.reference_prompt import organize,standalone,prompt_facts


def test_style_transfer_excludes_donor_identity_source_rendering_and_unrequested_background():
    one=dict(subject='黄色角色',appearance='圆腹',pose='抱头',style='3D光滑材质',scene='透明',uncertainties='')
    two=dict(one,subject='紫发少女',appearance='长袜',pose='站立',style='日式二维线稿',scene='纯白')
    facts=prompt_facts('将图一的人物风格改为图二风格，保留图一外形与动作',{1:one,2:two})
    text=json.dumps(facts,ensure_ascii=False)
    assert '黄色角色' in text and '抱头' in text and '日式二维线稿' in text
    assert all(token not in text for token in ('3D光滑','紫发少女','长袜','纯白'))
    background=prompt_facts('将图一的人物风格改为图二风格，保留图一背景',{1:dict(one,scene='森林'),2:two})
    assert background['subject_to_keep']['scene']=='森林'


def test_images_are_observed_separately_and_only_text_reaches_prompt_composer(tmp_path):
    refs={1:tmp_path/'one.png',2:tmp_path/'two.png'}
    for p in refs.values():Image.new('RGB',(8,8),'yellow').save(p)
    session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    observation=dict(subject='黄色圆润卡通角色',appearance='绿眼，圆形浅色腹部',pose='双手抱头',style='日式动画平涂',scene='纯色背景',uncertainties='')
    prompt='黄色圆润的卡通角色，绿色眼睛、浅色圆腹，保持双手抱头的姿势，采用日式动画平涂画法。'
    session.complete.side_effect=[(json.dumps(observation),{}),(json.dumps(observation),{}),
        (json.dumps(dict(positive_prompt=prompt)),{}),(json.dumps(dict(positive_prompt='A round yellow cartoon character with green eyes and a pale round belly, holding both hands on its head, in Japanese anime cel shading.',negative_prompt='')), {})]
    result=organize({},'保留图1的角色和动作，采用图2的画风','',refs,None,tmp_path/'plan',threading.Event(),lambda *_:None,session_factory=lambda *_:session)
    requests=[call.args[0] for call in session.complete.call_args_list]
    for request in requests[:2]:
        content=request[1]['content'];assert sum(item['type']=='image_url' for item in content)==1
    for request in requests[2:]:assert 'image_url' not in json.dumps(request)
    assert result['images_read'] and not result['joint_visual_analysis']
    assert standalone(result['plan']['positive_prompt']) and standalone(result['english']['positive'])
    assert set(result['observations'])=={1,2} and result['plan']['negative_prompt']==''


@pytest.mark.parametrize('text',['将图一人物改成抱头','Keep Image 2 style','参考图里的少女','第一张图的角色','该图人物'])
def test_unresolved_references_are_rejected(text):assert not standalone(text)


def test_bad_composed_prompt_does_not_write_a_ready_result(tmp_path):
    ref=tmp_path/'one.png';Image.new('RGB',(8,8),'blue').save(ref)
    session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    observation={k:'' for k in ('subject','appearance','pose','style','scene','uncertainties')}
    session.complete.side_effect=[(json.dumps(observation),{}),(json.dumps(dict(positive_prompt='让图1人物抱头')), {})]
    with pytest.raises(ValueError,match='指代'):
        organize({},'让图1人物抱头','',{1:ref},None,tmp_path/'plan',threading.Event(),lambda *_:None,session_factory=lambda *_:session)
    assert not (tmp_path/'plan/result.json').exists()


def test_api_production_uses_reviewed_prompt_instead_of_raw_requirement(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import patch
    from aipictures.smart_generation import generate
    params=dict(user_prompt='将图一角色改为抱头',user_negative='',production_prompt='A purple-haired character holding both hands on her head.',production_negative='',output_background='opaque')
    with patch('aipictures.smart_generation.generate_image',return_value={}) as render,patch('aipictures.general_image.finish_output',return_value={'ok':True}):
        generate(tmp_path,{},params,None,SimpleNamespace(key='fixture-not-a-key'),None,None,threading.Event(),lambda *_:None)
    assert render.call_args.args[2]==params['production_prompt'] and render.call_args.args[3]==''
