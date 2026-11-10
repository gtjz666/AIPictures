import json
import threading
from unittest.mock import Mock
from pathlib import Path
from PIL import Image
import pytest
from aipictures.video_edit import organize,compile_prompt,bind_labels
from aipictures.motion_native_graph import build,encoding,MODEL,ENCODER,VAE


def test_direct_edit_keeps_requested_style_out_of_negative_and_does_not_rewrite(tmp_path):
    refs={1:tmp_path/'one.png',4:tmp_path/'style.png'}
    for path in refs.values():Image.new('RGB',(16,24),'blue').save(path)
    request='人物采用图1，图4只提供Q版比例和线条；不要蓝发，动作与镜头跟随源视频。'
    model=Mock(side_effect=AssertionError('No second VLM rewrite for source-video editing'))
    script=organize({},request,30,'bright',refs,tmp_path/'request',threading.Event(),lambda *_:None,session_factory=model)
    assert script['overview']==request and script['shots'][0]['visual']==request
    assert 'Q版' not in script['negative_prompt'] and script['video_edit']
    model.assert_not_called()
    data=json.loads((tmp_path/'request/request.json').read_text('utf-8'))
    assert not data['video_content_analyzed'] and len(data['references'])==2


def test_numbered_picture_gaps_are_bound_for_real_reference_order():
    refs=[dict(number=1),dict(number=4)]
    text=compile_prompt('将人物换成图1，画风取图4。',refs)
    assert '<Picture 1>' in text and '<Picture 2>' in text and '<Picture 4>' not in text
    assert '<Video 1>' in text and 'source performance' in text
    assert bind_labels('不要图4的发型',refs)=='不要<Picture 2>的发型'
    with pytest.raises(ValueError):compile_prompt('人物换成图2',refs)


def test_each_reference_picture_has_a_real_independent_input():
    info={key:{} for key in ('MiniMaxH3ReferenceToVideo','AIPicturesMotionFrames','BasicGuider','BasicScheduler','SamplerCustomAdvanced','AIPicturesSaveConditioning')}
    for node,field,name in [('UNETLoader','unet_name',MODEL),('CLIPLoader','clip_name',ENCODER),('VAELoader','vae_name',VAE)]:
        info[node]={'input':{'required':{field:[[name]]}}}
    graph=build(info,'edit',1,512,768,56,'frames.json',['person.png','style.png','background.png'])
    inputs=graph['references']['inputs']
    assert [inputs[f'ref_images.ref_image_{i}'] for i in range(3)]==[['character',0],['reference_2',0],['reference_3',0]]
    assert inputs['ref_videos.ref_video_0']==['motion',0]
    saved=encoding(info,'edit',1,512,768,56,'frames.json',['person.png','style.png'])
    assert saved['reference_2']['inputs']['image']=='style.png' and 'model' not in saved


def test_eight_second_source_edit_does_not_start_two_chained_samplers(tmp_path):
    from unittest.mock import patch
    from aipictures.video_edit_chain import generate
    params=dict(seconds=8);cancel=threading.Event();emit=lambda *_:None
    with patch('aipictures.motion_native_backend.generate',return_value=dict(video=None,native_frames=[])) as single, \
         patch('aipictures.video_chain.generate',side_effect=AssertionError('Short edit must use one native invocation')):
        result=generate(tmp_path,params,cancel,emit)
    single.assert_called_once_with(tmp_path,params,cancel,emit)
    assert result['backend']=='H3/dedicated-Ref2VA-video-edit'
