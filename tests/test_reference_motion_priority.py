"""Video-first guidance reaches the real Ref2VA graph without a model run."""
import json
import threading

import pytest
from PIL import Image

from aipictures.motion_guide import prompt
from aipictures.prompt_timeline import (TITLE,REFERENCE_TITLE,MANUAL_TITLE,
                                       corrected_rows,remove_owned_timeline)


def row(start,end,text):
    return dict(start=start,end=end,description=text)


def test_only_changed_intervals_override_the_visual_reference():
    original=[row(0,1,'抬手'),row(1,2,'停顿'),row(2,4,'收手')]
    assert corrected_rows(original,original)==[]
    # A shorter/longer output may split untouched rows, without approving them.
    edited=[row(0,1,'右手挥向镜头'),row(1,2,'停顿'),row(2,3,'收手')]
    assert corrected_rows(edited,original)==edited[:1]
    assert corrected_rows([row(1,1.5,'停顿')],original)==[]
    assert corrected_rows([row(.5,2,'停顿')],original)==[row(.5,2,'停顿')]
    assert corrected_rows([row(1,2,'抬手')],original)==[row(1,2,'抬手')]


@pytest.mark.parametrize('title',[TITLE,REFERENCE_TITLE,MANUAL_TITLE])
def test_owned_footer_cleanup_keeps_ordinary_user_constraints(title):
    text='用户要求固定机位。\n\n'+title+'\n0.000–1.000秒：抬手\n\n保留水彩线条。'
    clean=remove_owned_timeline(text)
    assert clean=='用户要求固定机位。\n\n保留水彩线条。'


def test_visual_priority_preserves_explicit_user_changes_and_reference_tags():
    text='改用近景，镜头向左移动。\n'+MANUAL_TITLE+'\n1.000–2.000秒：右手向上挥。'
    result=prompt(text,True)
    assert text in result and '<Picture 1>' in result and '<Video 1>' in result
    assert 'highest-priority reference' in result and 'Only explicit user changes override' in result
    assert 'pauses, repeated gestures' in result
    assert 'Keep the complete subject in view' not in result
    assert 'without cuts or sudden zoom' not in result
    assert 'Use the actual guide frames rather than an inferred action description' in result
    assert '<Picture 1>' not in prompt('黄色机器人',False)


@pytest.mark.parametrize('role,usage,marker',[
    ('appearance','','Its still pose and composition do not define the animation'),
    ('style','','only for visual style'),
    ('custom','只借用衣服配色，不复制人物和站姿','not automatically for identity or pose'),
])
def test_actual_backend_encodes_video_and_selected_image_role(tmp_path,monkeypatch,role,usage,marker):
    from aipictures import motion_native_backend as backend,motion_native_graph as native
    source=tmp_path/'source.gif'
    Image.new('RGB',(16,24),'red').save(source,save_all=True,
        append_images=[Image.new('RGB',(16,24),'blue')],duration=[1000,1000])
    image=tmp_path/'image.png';Image.new('RGBA',(16,24),(10,100,230,128)).save(image)
    image_bytes=image.read_bytes();sessions=[]
    info={n:{} for n in ('MiniMaxH3ReferenceToVideo','AIPicturesMotionFrames','BasicGuider',
        'BasicScheduler','SamplerCustomAdvanced','AIPicturesSaveConditioning','AIPicturesLoadConditioning')}
    for node,field,name in [('UNETLoader','unet_name',native.MODEL),('CLIPLoader','clip_name',native.ENCODER),
                            ('VAELoader','vae_name',native.VAE)]:
        info[node]={'input':{'required':{field:[[name]]}}}

    class Session:
        def __init__(self,config,folder,cancel,emit):
            self.folder=folder;self.input=folder/'input';self.output_dir=folder/'output'
            self.info=info;self.client=self;self.closed=False
        def __enter__(self):
            if sessions:assert sessions[-1].closed
            sessions.append(self);self.input.mkdir(parents=True);self.output_dir.mkdir();return self
        def __exit__(self,*_):self.closed=True
        def check(self):pass
        def generate(self,graph,folder,emit,cancel,**kwargs):
            folder.mkdir(parents=True)
            if self.folder.name=='native_encode':
                refs=graph['references']['inputs'];encoded=refs['prompt']
                assert marker in encoded and '<Video 1>' in encoded
                assert '1.000–2.000秒：右手挥向镜头' in encoded
                assert usage in encoded and 'Avoid: 不要文字' in encoded
                assert refs['ref_videos.ref_video_0']==['motion',0]
                assert refs['ref_images.ref_image_0']==['character',0]
                assert refs['vae']==['vae',0] and refs['clip']==['clip',0]
                frames=json.loads((self.input/graph['motion']['inputs']['manifest']).read_text('utf-8'))
                assert frames['fps']==24 and len(frames['frames'])==56
                packet=self.output_dir/'conditioning';packet.mkdir()
                (packet/'conditioning.json').write_text('{}')
                (packet/'conditioning.safetensors').write_bytes(b'lossless-condition-fixture')
                return {}
            assert graph['references']['class_type']=='AIPicturesLoadConditioning'
            assert (self.input/'conditioning/conditioning.safetensors').read_bytes()==b'lossless-condition-fixture'
            paths=[]
            for i in range(56):
                path=folder/f'{i}.png';Image.new('RGB',(16,24),'green').save(path);paths.append(str(path))
            return dict(images=paths)

    monkeypatch.setattr(backend,'NativeSession',Session)
    monkeypatch.setattr(backend,'release_shared',lambda *a,**kw:None)
    params=dict(seconds=2.,seed=12,prompt='蓝色机器人\n'+MANUAL_TITLE+'\n1.000–2.000秒：右手挥向镜头',
        negative='不要文字',reference=str(image),reference_role=role,reference_usage=usage,
        motion_reference=str(source),motion_native_settings={'validated':True},defer_exports=True)
    folder=tmp_path/'job';folder.mkdir()
    result=backend.generate(folder,params,threading.Event(),lambda *_:None)
    graph=json.loads((folder/'workflow.json').read_text('utf-8'))
    assert (folder/'prompt.txt').read_text('utf-8')==graph['references']['inputs']['prompt']
    assert image.read_bytes()==image_bytes
    assert all(s.closed for s in sessions) and result['staged'] and not result['video']


def test_custom_usage_must_be_explicit():
    with pytest.raises(ValueError,match='自定义用法'):
        prompt('机器人',True,reference_role='custom')
