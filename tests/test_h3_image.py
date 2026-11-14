import json
import threading
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from aipictures import h3_image as h3
from aipictures.multi_reference import bind_text,image_ids


def config():
    return dict(encoder=dict(path='encoder.safetensors'),models=[dict(path='image.safetensors'),dict(path='vae.safetensors')])


def test_picture_binding_compacts_gallery_gaps_once_and_supports_sixteen():
    raw='保留图十二的角色，使用图十六的画风；<Picture 12> and Image 16'
    assert image_ids(raw)=={12,16}
    text=h3.instruction(raw,{12:'first',16:'second'})
    assert text=='保留<Picture 1>的角色，使用<Picture 2>的画风；<Picture 1> and <Picture 2>'
    with pytest.raises(ValueError,match='图1'):h3.instruction('图1的角色',{12:'only'})
    assert bind_text('图十一的角色',[11])=='Image 1的角色'


@pytest.mark.parametrize('count',[0,1,2,16])
def test_official_native_conditioning_inputs_are_separate_and_ordered(count):
    c=config();names=[f'{i}.png' for i in range(count)]
    g=h3.encode_graph(c,'instruction',2048,2048,names)
    refs={k:v for k,v in g['condition']['inputs'].items() if k.startswith('images.')}
    assert len(refs)==count
    assert refs=={f'images.image_{i}':[f'image_{i}',0] for i in range(1,count+1)}
    assert all(g[f'image_{i}']['inputs']['image']==names[i-1] for i in range(1,count+1))
    s=h3.sample_graph(c,23)['sample']['inputs']
    assert (s['steps'],s['cfg'],s['sampler_name'],s['scheduler'],s['denoise'])==(6,1.,'euler','simple',1.)
    assert s['latent_image']==['condition',1] and s['positive']==['condition',0]
    assert h3.decode_graph(c)['decode']['inputs']['samples']==['condition',1]
    assert not any('control' in n['class_type'].lower() or 'lora' in n['class_type'].lower() for n in g.values())


def test_canvas_preserves_aspect_and_invalid_requests_fail_before_model():
    w,h=h3.canvas(400,600)
    assert abs(w/h-2/3)<.02 and 4_000_000<w*h<4_500_000 and w%32==h%32==0
    h3.validate(w,h,4,{i:None for i in range(1,17)})
    for values in [(513,2048,0,{}),(4096,8192,0,{}),(2048,2048,-1,{}),(2048,2048,1,{17:None})]:
        with pytest.raises(ValueError):h3.validate(*values)


def test_reference_preparation_is_text_only_and_keeps_user_operation(tmp_path):
    from aipictures.h3_image_prompt import organize
    source=tmp_path/'reference.png';Image.new('RGB',(32,32)).save(source)
    brief='将图一的画风改为图十二的画风，保留图一姿势，不要改变背景。'
    class Session:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def complete(self,messages,**kwargs):
            assert 'image_url' not in json.dumps(messages)
            return json.dumps(dict(positive_prompt='Change Image 1 to the art style of Image 12, keep the pose of Image 1 and do not change the background.',negative_prompt='')),{}
    with patch('aipictures.reference_prompt.organize',side_effect=AssertionError('no image analysis')):
        result=organize({},brief,{1:source,12:source},tmp_path/'prompt',threading.Event(),lambda *_:None,session_factory=Session)
    assert result['plan']['positive_prompt']==brief
    assert not result['plan']['negative_prompt'] and not result['images_read']
    assert image_ids(result['english']['positive'])=={1,12}


def test_no_restart_or_duplicate_attempt_for_an_existing_job(tmp_path):
    from aipictures.h3_image_runtime import generate
    (tmp_path/'h3-image-started.json').write_text('{}')
    with patch('aipictures.h3_image_runtime.Session') as session:
        with pytest.raises(ValueError,match='提交过'):generate(tmp_path,{},threading.Event(),lambda *_:None)
        session.assert_not_called()


def test_large_file_hashing_never_materializes_the_file(tmp_path):
    import hashlib
    from aipictures.workflow_library import digest
    path=tmp_path/'weight';path.write_bytes(b'model bytes'*10000)
    with patch.object(Path,'read_bytes',side_effect=AssertionError('unbounded file read')):
        assert digest(path)==hashlib.sha256(b'model bytes'*10000).hexdigest()


def test_verified_model_receipt_invalidated_on_file_change(tmp_path):
    from aipictures.h3_image_runtime import verify_models,_verified
    from aipictures.workflow_library import digest
    rows=[]
    for n in range(3):
        p=tmp_path/str(n);p.write_bytes(bytes([n])*32)
        rows.append(dict(path=str(p),bytes=32,sha256=digest(p)))
    c=dict(models=rows[:2],encoder=rows[2]);records=verify_models(c,tmp_path,threading.Event())
    c['verified_models']=records;_verified.clear()
    with patch('aipictures.h3_image_runtime.digest',side_effect=AssertionError('unchanged model already verified')):
        assert verify_models(c,tmp_path,threading.Event())==records
    Path(rows[0]['path']).write_bytes(b'x'*32)
    with pytest.raises(ValueError,match='校验失败'):verify_models(c,tmp_path,threading.Event())


def test_cancelled_private_startup_releases_only_owned_process(tmp_path):
    import sys
    from aipictures.engine import Cancelled
    from aipictures.h3_image_runtime import Session
    source=tmp_path/'source';source.mkdir();(source/'main.py').write_text('import time;time.sleep(60)')
    cancel=threading.Event();events=[]
    def emit(kind,data):
        events.append(kind)
        if kind=='h3_image_process':threading.Timer(.2,cancel.set).start()
    session=Session(dict(python=sys.executable,source=str(source),model_paths=str(tmp_path/'paths.yaml')),tmp_path/'owned',cancel,emit)
    with pytest.raises(Cancelled):
        with session:raise AssertionError('cancel must occur during startup')
    assert session.child.poll() is not None and session.owner.handle is None
    assert json.loads((session.folder/'process.json').read_text())['status']=='stopped'


def test_actual_qt_gallery_binding_and_generation_gate():
    import os,subprocess,sys
    result=subprocess.run([sys.executable,'-m','tools.verify_h3_image_ui'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=60)
    assert result.returncode==0,(result.stdout+result.stderr).decode('utf-8','replace')


def test_registration_rejects_unverified_desktop_evidence(tmp_path):
    from tools.register_h3_image import register
    (tmp_path/'machine.json').write_text('{}')
    (tmp_path/'acceptance.json').write_text(json.dumps([dict(actual_qt=False,actual_models=False)]))
    with pytest.raises(ValueError,match='实际桌面'):
        register(tmp_path/'machine.json',tmp_path,tmp_path/'production')
    assert not (tmp_path/'production/h3-image-settings.json').exists()
