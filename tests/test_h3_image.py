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


def test_decode_uses_cpu_only_on_the_validated_twelve_gib_cards():
    from aipictures.comfy_vram import GIB
    from aipictures.h3_image_runtime import decode_on_cpu
    assert decode_on_cpu(12*GIB) is True
    assert decode_on_cpu(12282*1024**2) is True
    assert decode_on_cpu(16*GIB) is False
    assert decode_on_cpu(24*GIB) is False
    assert decode_on_cpu(None) is True


def test_cpu_decode_session_never_starts_a_gpu_backend(tmp_path):
    from aipictures.h3_image_runtime import Session
    config=dict(python='python',model_paths='models.yaml',source=str(tmp_path))
    cpu=Session(config,tmp_path/'cpu',threading.Event(),lambda *_:None,cpu=True)
    cpu.input=tmp_path/'input';cpu.output=tmp_path/'output'
    command=cpu.command(1234)
    assert '--cpu' in command and '--reserve-vram' not in command
    gpu=Session(config,tmp_path/'gpu',threading.Event(),lambda *_:None,cpu=False)
    gpu.input=tmp_path/'input';gpu.output=tmp_path/'output'
    command=gpu.command(1234)
    assert '--cpu' not in command and command[-2:]==['--reserve-vram','3.0']


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


def test_short_reference_edit_fixes_the_base_order_without_renumbering_the_gallery(tmp_path):
    pose = tmp_path / 'pose.png'; subject = tmp_path / 'subject.png'
    Image.new('RGB', (1200, 1300)).save(pose)
    Image.new('RGB', (800, 1200)).save(subject)
    refs = {1:pose, 3:subject}
    text, order, edit = h3.reference_edit('将图三的人物动作和面部表情改成图一的', refs)
    assert order == [3,1] and list(refs) == [1,3]
    assert edit['base_slot'] == 3 and edit['source_slot'] == 1
    assert '将<Picture 1>的人物动作和面部表情改成<Picture 2>的' in text
    assert '<Picture 2>仅提供动作姿势、面部表情' in text
    assert h3.reference_edit_canvas(refs,edit,*h3.canvas(1200,1300)) == h3.canvas(800,1200)
    assert h3.reference_edit_canvas(refs,edit,832,1280) == (832,1280)


def test_reference_edit_keeps_appearance_and_style_roles_distinct():
    refs = {1:None, 2:None, 7:None}
    _, order, edit = h3.reference_edit('保留图2的人物和服装，采用图7的画风', refs)
    assert order == [2,1,7] and edit['attributes'] == ['美术风格']
    _, order, edit = h3.reference_edit('将图2人物的动作、表情、镜头构图和背景改成图1的', refs)
    assert order == [2,1,7] and edit['attributes'] == ['动作姿势','面部表情','构图','背景']
    text, order, edit = h3.reference_edit('底图：图2。融合图1的服装和图7的画风。', refs)
    assert order == [2,1,7] and edit['base_slot'] == 2
    assert '融合<Picture 2>的服装和<Picture 3>的画风' in text
    with pytest.raises(ValueError, match='说明改哪张图'):
        h3.reference_edit('把图2的动作改成另一张图里的', refs)
    assert h3.reference_edit('给图2的人物画上帽子', {2:None}) == ('给<Picture 1>的人物画上帽子',[2],None)


def test_reference_guide_reads_each_role_separately_and_preserves_the_request(tmp_path):
    from aipictures.h3_reference_guide import prepare
    from aipictures.workflow_library import digest
    refs = {}
    for slot, color in [(1,'yellow'), (2,'red')]:
        path = tmp_path / f'{slot}.png'
        Image.new('RGB', (32,32), color).save(path)
        refs[slot] = path
    text, order, edit = h3.reference_edit('把图2的动作改成图1的', refs)
    frozen = {slot:dict(path=refs[slot],sha256=digest(refs[slot]),model_input=i)
              for i,slot in enumerate(order,1)}
    folder = tmp_path/'guide'
    calls = []
    class GuideSession:
        def __init__(self,*args): pass
        def __enter__(self): return self
        def __exit__(self,*args): calls.append('released')
        def complete(self, messages, **kwargs):
            material = messages[-1]['content']
            calls.append(material)
            return json.dumps(dict(description='red outfit' if len(calls)==1 else 'right hand raised')), {}
    effective = prepare({},edit,frozen,text,folder,threading.Event(),lambda *_:None,session_factory=GuideSession)
    assert calls[-1]=='released' and len(calls)==3
    assert calls[0][1]['image_url']['url']!=calls[1][1]['image_url']['url']
    assert 'distinguishing features to keep' in calls[0][0]['text']
    assert 'Describe only these features' in calls[1][0]['text']
    assert 'red outfit' in effective and 'right hand raised' in effective
    assert effective.endswith('把<Picture 1>的动作改成<Picture 2>的')
    assert json.loads((folder/'result.json').read_text('utf-8'))['guide_released']


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


def test_failed_job_assignment_reaps_gated_child_and_closes_log(tmp_path):
    import sys
    from aipictures.h3_image_runtime import Session
    source=tmp_path/'source';source.mkdir()
    # The gate must never let this module run when process ownership fails.
    (source/'main.py').write_text("from pathlib import Path;Path('unexpected').touch()")
    session=Session(dict(python=sys.executable,source=str(source),model_paths='unused'),
                    tmp_path/'owned',threading.Event(),lambda *_:None)
    with patch('aipictures.h3_image_runtime.OwnedProcessJob',side_effect=OSError('job assignment denied')):
        with pytest.raises(OSError,match='job assignment denied'):
            with session:raise AssertionError('must not start')
    assert session.child.poll() is not None and session.log.closed
    assert session.child.stdin.closed and not (source/'unexpected').exists()
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
