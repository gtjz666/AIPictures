import json,threading
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from aipictures.reference_subject import prepare
from aipictures.engine import Cancelled
from aipictures.workflow_library import digest


def test_existing_alpha_is_preserved_source_unchanged_and_second_request_uses_verified_cache(tmp_path):
    source=tmp_path/'reference.png';im=Image.new('RGBA',(24,32),(0,0,0,0))
    im.paste((12,150,240,255),(5,4,19,29));im.save(source);original=digest(source)
    first=prepare(source,tmp_path/'data',None,threading.Event(),lambda *_:None)
    assert not first['cache_hit'] and first['method']=='original_alpha' and first['worker_returncode']==0
    assert first['bounds']==[5,4,19,29] and digest(source)==original
    with Image.open(first['prepared']) as result:assert result.size==(14,25) and result.getpixel((6,6))==(12,150,240)
    with patch('aipictures.reference_subject.subprocess.Popen',side_effect=AssertionError('No repeated worker')):
        second=prepare(source,tmp_path/'data',None,threading.Event(),lambda *_:None)
    assert second['cache_hit'] and second['prepared_sha256']==first['prepared_sha256']
    # An invalid cached result cannot silently replace the reference or start a new inference.
    Path(first['prepared']).write_bytes(b'corrupt')
    with patch('aipictures.reference_subject.subprocess.Popen') as spawn,pytest.raises(ValueError,match='校验'):
        prepare(source,tmp_path/'data',None,threading.Event(),lambda *_:None)
    spawn.assert_not_called()


def test_opaque_reference_without_model_cannot_silently_retain_scene(tmp_path):
    source=tmp_path/'photo.png';Image.new('RGB',(20,20),'blue').save(source)
    with pytest.raises(ValueError,match='BiRefNet'):prepare(source,tmp_path/'data',None,threading.Event(),lambda *_:None)


def test_cancelled_subject_preparation_does_not_start_process(tmp_path):
    cancel=threading.Event();cancel.set()
    with patch('aipictures.reference_subject.subprocess.Popen') as spawn,pytest.raises(Cancelled):
        prepare(tmp_path/'missing',tmp_path,None,cancel,lambda *_:None)
    spawn.assert_not_called()


def test_invented_rendering_cannot_override_photo_but_explicit_user_style_is_allowed():
    from aipictures.reference_prompt import validate_structure_style
    with pytest.raises(ValueError,match='画风'):validate_structure_style('女性，白衬衫，3D渲染风格','保留图1外形，采用图2姿势')
    validate_structure_style('女性，白衬衫，3D渲染风格','采用图2姿势，改为3D渲染')
    validate_structure_style('粉色卡通怪物，白色腹部','保留主体外观，采用图2姿势')


def test_cancel_during_model_verification_does_not_start_worker(tmp_path):
    source=tmp_path/'photo.png';Image.new('RGB',(20,20),'blue').save(source)
    model=tmp_path/'model';model.write_bytes(b'fixture');cancel=threading.Event()
    def verify(*_):cancel.set();return 'fixture-sha'
    with patch('aipictures.reference_subject.model_digest',side_effect=verify),patch('aipictures.reference_subject.subprocess.Popen') as spawn,pytest.raises(Cancelled):
        prepare(source,tmp_path/'data',dict(path=str(model)),cancel,lambda *_:None)
    spawn.assert_not_called()
