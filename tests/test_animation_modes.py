import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
import pytest

from aipictures.animation_actions import PRESET_ACTIONS as ACTIONS, output_indices,stage_label,ONE_SHOT_ACTIONS
from aipictures.animation_status import monitor_text
from aipictures.character_profile import rig_document
from aipictures.motion_clip import make_clip, sample_clip
from aipictures.pose_animation import generate
from tests.test_generation_reference import analysis_geometry


@pytest.mark.parametrize('action', ACTIONS)
@pytest.mark.parametrize('count', [8, 16])
def test_every_mode_uses_full_native_conditions_and_separate_decode(tmp_path, action, count):
    source = tmp_path/'reference.png'
    Image.new('RGB',(768,1024),(180,90,40)).save(source)
    rig=tmp_path/'rig.json';rig.write_text(json.dumps(rig_document()))
    latent=tmp_path/'data.latent';latent.write_bytes(b'saved-samples')
    client=Mock();client.url='http://127.0.0.1:8188'
    client.discover.return_value={'object_info':{}}
    client.upload_image.side_effect=lambda p,**kw:Path(p).name
    client.generate.side_effect=[{'images':[],'latents':[str(latent)],'prompt_id':'sample'},
        {'images':[str(source)]*(count*4+1),'prompt_id':'decode'}]
    folder=tmp_path/'animation';folder.mkdir()
    with patch('aipictures.pose_animation.prepare_motion_reference',return_value=dict(analysis_geometry(),rig=str(rig))), \
         patch('aipictures.pose_animation.bind_model_names'),patch('aipictures.pose_animation.release_idle_models',return_value={}), \
         patch('aipictures.animation_decode.release_idle_models',return_value={}):
        generate(client,folder,'同一角色','重影',42,count,8,Mock(),threading.Event(),source,
                 action=action,raw_only=True)
    sample,decode=client.generate.call_args_list
    graph=sample.args[0]
    assert graph['8']['inputs']['length']==count*4+1
    assert graph['8']['inputs']['width']==768 and graph['8']['inputs']['height']==1024
    assert ACTIONS[action][1] in graph['5']['inputs']['text']
    assert graph['11']['inputs']['steps']==20 and graph['11']['inputs']['cfg']==1
    assert 'acceleration' not in graph
    assert {n['class_type'] for n in decode.args[0].values()}=={'LoadLatent','VAELoader','VAEDecode','SaveImage'}
    assert sample.kwargs['timeout']==float('inf') and decode.kwargs['timeout']==float('inf')
    poses=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((folder/'poses').glob('*.json'))]
    assert len(poses)==count*4+1
    assert any(p['joints']!=poses[0]['joints'] for p in poses[1:-1])
    manifest=json.loads((folder/'sequence.json').read_text(encoding='utf-8'))
    assert manifest['action']==action and manifest['color_mode']=='original'
    assert manifest['sampling_prompt_id']=='sample' and manifest['decode_prompt_id']=='decode'
    assert manifest['loop']==(action not in ONE_SHOT_ACTIONS)
    assert manifest['temporal_sampling']['latent_time_cells']>=count
    assert manifest['temporal_sampling']['post_frame_interpolation'] is False
    assert 'sampling_wait_and_download_seconds' in manifest['timings']
    assert 'decode_wait_and_download_seconds' in manifest['timings']


def test_jump_retains_landing_endpoint_and_edited_final_key():
    assert output_indices('walk',8,17)==[0,2,4,6,8,10,12,14]
    assert output_indices('jump',8,17)==[0,2,5,7,9,11,14,16]
    assert stage_label('jump',1)=='恢复站立'
    jump=make_clip(rig_document(),'a'*64,'jump')
    assert jump['frames'][0]['joints']==jump['frames'][-1]['joints']
    assert jump['frames'][-1]['phase']==1 and jump['frames'][-1]['stage']=='恢复站立'
    jump['edited']=True
    jump['frames'][-1]['joints']['right_wrist'][0]+=15
    assert sample_clip(jump,1)['joints']==jump['frames'][-1]['joints']
    assert sample_clip(jump,.5)['joints']!=jump['frames'][0]['joints']


def test_stage_text_distinguishes_queue_prepare_sampling_and_cancel():
    assert '采样前' in monitor_text('executing',{'node':'8'},{'8':{'class_type':'WanAnimateToVideo'}})
    assert '等待共享引擎' in monitor_text('monitor_status',{'state':'queued'})
    assert '采样' in monitor_text('monitor_status',{'state':'running','node_type':'KSampler'})
    assert '确认取消' in monitor_text('monitor_status',{'state':'cancelling'})
    assert monitor_text('progress',{'value':1,'max':20}) is None
