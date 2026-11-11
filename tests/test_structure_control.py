import json,threading,subprocess,os,sys
from unittest.mock import Mock
from pathlib import Path
import pytest
from PIL import Image
from aipictures.structure_control import resolve,build,ADAPTER
from aipictures.workflow import ImageRequest
from aipictures.flux_klein import UNET
from tests.test_image_choice_retirement import model_info

@pytest.mark.parametrize('brief,expected',[
    ('将图1中的人物替换为图2中的角色，保持图1的姿势和构图',(1,2)),
    ('让图一的角色采用图二的姿势',(2,1)),
    ('图1为结构参考，图2为主体外观，保持姿势',(1,2)),
    ('将图一的人物美术风格修改为图二的美术风格，保留图一的人物动作与人物外形',None),
    ('将图1的人物改为双手抱头，保留人物外形',None)])
def test_role_direction_is_taken_from_request_not_visual_guesses(brief,expected):
    v=resolve(brief,{1:'a',2:'b'})
    assert (v['structure'],v['identity'])==expected if expected else v is None

def test_explicit_source_and_unsupported_extra_images_are_not_silently_dropped():
    assert resolve('机械臂替换材质',{1:'a'},'1')['identity']==1
    assert resolve('保留姿势',{1:'a',2:'b'},'off') is None
    with pytest.raises(ValueError):resolve('换主体',{1:'a',2:'b',3:'c'},'1')
    with pytest.raises(ValueError):resolve('换主体',{1:'a'},'4')
    with pytest.raises(ValueError):resolve('换主体',{},'1')
    assert resolve('将图1的人物替换为图2中的角色',{1:'a',2:'b'},'2')['identity']==1
    assert resolve('将图1的人物换成图2的风格，保留图1的姿势',{1:'a',2:'b'}) is None

def test_trained_adapter_is_really_on_sampler_model_path():
    info=model_info();info['LoraLoaderModelOnly']={'input':{'required':{'lora_name':[[ADAPTER]]}}}
    req=ImageRequest(UNET,'A purple-haired anime woman.','',512,512,4,1.,8,'euler','flux2')
    graph,mapping=build(req,info,{1:'pose.png',2:'character.png'},dict(structure=1,identity=2),dict(validated=True))
    assert graph['image_1']['inputs']['image']=='__structure_depth__'
    assert graph['image_2']['inputs']['image']=='character.png'
    assert graph['structure_adapter']['inputs']['model']==['model',0]
    node='release' if 'release' in graph else 'guider'
    assert graph[node]['inputs']['model']==['structure_adapter',0]
    assert 'refcontrol' in graph['text']['inputs']['text']
    from aipictures.lora_policy import plain_workflow
    assert 'structure_adapter' in plain_workflow(graph,trained_structure=True)
    assert 'structure_adapter' not in plain_workflow(graph)
    with pytest.raises(ValueError,match='验证'):build(req,info,{1:'a',2:'b'},dict(structure=1,identity=2),None)

def test_geometry_is_not_analyzed_by_language_model_or_copied_from_identity_pose(tmp_path):
    from aipictures.reference_prompt import organize
    refs={1:tmp_path/'geometry.png',2:tmp_path/'identity.png'}
    for p in refs.values():Image.new('RGB',(8,8),'blue').save(p)
    session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    observed=dict(subject='动漫女性',appearance='紫发白衬衫',pose='错误旧站姿',style='动漫线稿，角色正面站立',scene='白底',uncertainties='')
    session.complete.side_effect=[(json.dumps(observed),{}),(json.dumps(dict(positive_prompt='紫发白衬衫的动漫女性，姿态与构图遵循结构约束。')),{}),
        (json.dumps(dict(positive_prompt='A purple-haired anime woman in a white blouse, with pose and layout provided by structural conditioning.',negative_prompt='')), {})]
    result=organize({},'让图2角色采用图1姿势','',refs,None,tmp_path/'plan',threading.Event(),lambda *_:None,structure_binding=dict(structure=1,identity=2),session_factory=lambda *_:session)
    assert set(result['observations'])=={2} and session.complete.call_count==3
    composition=session.complete.call_args_list[1].args[0][1]['content']
    assert '错误旧站姿' not in composition and 'image_url' not in composition
    assert '正面站立' not in composition and '图1' not in composition and '图2' not in composition
    assert '动漫线稿' not in composition  # A guessed style must not override actual identity pixels.


def test_structure_native_queue_and_stale_edit_protocol():
    run=subprocess.run([sys.executable,'-m','tools.verify_structure_route'],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=60)
    assert run.returncode==0,(run.stdout+run.stderr).decode('utf-8','replace')


def test_nonconsecutive_gallery_numbers_are_remapped_to_private_model_inputs():
    info=model_info();info['LoraLoaderModelOnly']={'input':{'required':{'lora_name':[[ADAPTER]]}}}
    req=ImageRequest(UNET,'Use Image 4 identity and Image 2 geometry.','',512,512,4,1.,8,'euler','flux2')
    graph,mapping=build(req,info,{2:'pose',4:'subject'},dict(structure=2,identity=4),dict(validated=True))
    text=graph['text']['inputs']['text']
    assert 'Use Image 2 identity and Image 1 geometry.' in text and 'Image 4' not in text
    assert mapping['model_inputs'][0]['gallery_number']==2 and mapping['model_inputs'][1]['gallery_number']==4


def test_cancelled_extraction_does_not_start_a_worker(tmp_path):
    from aipictures.structure_control import extract
    from aipictures.engine import Cancelled
    from unittest.mock import patch
    cancel=threading.Event();cancel.set()
    with patch('aipictures.structure_control.subprocess.Popen') as spawn,pytest.raises(Cancelled):
        extract({},tmp_path/'source',tmp_path/'output',512,512,cancel,lambda *_:None)
    spawn.assert_not_called()


@pytest.mark.parametrize('size',[(0,512),(513,512),(4096,512),(True,512)])
def test_invalid_depth_canvas_rejected_before_model_loading(size):
    from aipictures.structure_worker import validate
    with pytest.raises(ValueError):validate(dict(width=size[0],height=size[1]))
