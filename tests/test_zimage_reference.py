"""Reference pixels must reach the sampler; ordinary img2img is not identity editing."""
import json
import math
import os
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock,patch

import pytest
from PIL import Image,ImageDraw

from aipictures import zimage
from aipictures.workflow import ImageRequest


def model_info():
    info={name:{} for name in ('EmptySD3LatentImage','ModelSamplingAuraFlow','ConditioningZeroOut',
        'LoadImage','ImageScale','VAEEncode','CLIPTextEncode','KSampler','VAEDecode','SaveImage')}
    for node,field,name in (('UNETLoader','unet_name',zimage.UNET),('CLIPLoader','clip_name',zimage.ENCODER),('VAELoader','vae_name',zimage.VAE)):
        info[node]={'input':{'required':{field:[[name]]}}}
    return info


def test_reference_pixels_replace_empty_latent_without_loading_another_model():
    info=model_info();info['AIPicturesReleaseCompletedEncoders']={}
    request=ImageRequest(zimage.UNET,'同一角色，上衣改为蓝色','水印',768,1024,seed=123)
    graph,mapping=zimage.build(request,info,'uploaded.png',.65)
    assert graph['reference']['inputs']['image']=='uploaded.png'
    assert graph['latent']['class_type']=='VAEEncode'
    assert graph['latent']['inputs']['pixels']==['reference_canvas',0]
    assert graph['reference_canvas']['inputs']['image']==['reference',0]
    assert (graph['reference_canvas']['inputs']['width'],graph['reference_canvas']['inputs']['height'])==(768,1024)
    assert graph['sample']['inputs']['latent_image']==['latent',0]
    assert graph['sample']['inputs']['denoise']==.65 and graph['sample']['inputs']['seed']==123
    assert graph['sample']['inputs']['model']==['release',0]
    assert mapping['reference']==['reference'] and '上衣改为蓝色' in graph['text']['inputs']['text']
    assert not any(n['class_type']=='EmptySD3LatentImage' for n in graph.values())
    assert not any('flux' in str(n['inputs']).lower() or 'controlnet' in n['class_type'].lower() for n in graph.values())


def test_text_only_remains_independent_of_last_reference_strength():
    graph,mapping=zimage.build(ImageRequest('unused','森林',seed=2),model_info(),denoise=.2)
    assert not mapping['reference'] and 'reference' not in graph
    assert graph['latent']['class_type']=='EmptySD3LatentImage' and graph['sample']['inputs']['denoise']==1.


@pytest.mark.parametrize('strength',[0.,-.2,1.01,math.nan,math.inf])
def test_invalid_reference_strength_is_rejected(strength):
    with pytest.raises(ValueError,match='重绘幅度'):
        zimage.build(ImageRequest('unused','保持配色',seed=2),model_info(),'ref.png',strength)


def test_missing_reference_nodes_never_silently_drop_image():
    info=model_info();del info['VAEEncode']
    assert zimage.available(info) and not zimage.reference_available(info)
    with pytest.raises(ValueError,match='缺少模型或'):
        zimage.build(ImageRequest('unused','保持配色',seed=2),info,'ref.png',.45)


def test_reference_fit_preserves_aspect_and_composites_existing_alpha_only():
    source=Image.new('RGBA',(20,60),(0,255,0,0))
    ImageDraw.Draw(source).rectangle((2,5,17,54),fill=(255,255,255,255))
    before=source.tobytes();prepared=zimage.prepare_reference(source,64,64)
    assert prepared.mode=='RGB' and prepared.size==(64,64)
    assert prepared.getpixel((0,32))==(242,243,245) and prepared.getpixel((32,32))==(255,255,255)
    row=[x for x in range(64) if prepared.getpixel((x,32))==(255,255,255)]
    assert 10<len(row)<20  # Tall original was fitted and padded, not widened to the canvas.
    assert source.tobytes()==before


def test_smart_queue_rebinds_uploaded_reference_and_keeps_frozen_denoise(tmp_path):
    from aipictures.smart_generation import generate
    source=tmp_path/'source.png';Image.new('RGBA',(64,128),(255,255,255,255)).save(source)
    request=ImageRequest('unused','白色上衣改蓝色','水印',256,256,9,1.,123,'euler','simple')
    graph,mapping=zimage.build(request,model_info(),'__placeholder__',.7)
    params={**asdict(request),'model_family':'zimage','bindings':mapping,'denoise':.7,
        'reference_policy':'img2img','user_prompt':request.positive,'user_negative':request.negative,'output_background':'preserve'}
    client=Mock();client.upload_image.return_value='actual_uploaded.png';client.generate.return_value={'images':['protocol-test.png']}
    with patch('aipictures.engine_service.release_idle_models',return_value={}):
        generate(tmp_path,graph,params,None,None,source,client,threading.Event(),lambda *_:None)
    actual=client.generate.call_args.args[0]
    assert actual['reference']['inputs']['image']=='actual_uploaded.png'
    assert actual['sample']['inputs']['denoise']==.7 and actual['sample']['inputs']['seed']==123
    assert graph['reference']['inputs']['image']=='__placeholder__'
    with Image.open(client.upload_image.call_args.args[0]) as staged:
        assert staged.size==(256,256) and staged.mode=='RGB' and staged.getpixel((0,128))==(242,243,245)


def test_actual_qt_reference_selection_and_frozen_queue():
    result=subprocess.run([sys.executable,'-m','tests.live_zimage_reference'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONUTF8='1'),capture_output=True,timeout=40)
    assert result.returncode==0,result.stdout.decode('utf-8','replace')+result.stderr.decode('utf-8','replace')
