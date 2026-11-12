import json,threading
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from aipictures.engine import Cancelled
from aipictures.export_background import prepare,run
from aipictures.selected_frames import read_source,export_selection
from aipictures.workflow_library import digest

def test_cutout_frames_are_ready_before_picker_and_keep_raw_export_option(tmp_path):
    raw=tmp_path/'source.png';Image.new('RGB',(32,48),(150,170,190)).save(raw)
    before=raw.read_bytes();model=tmp_path/'model';model.write_bytes(b'fixture')
    folder=tmp_path/'prepared';folder.mkdir();data=dict(status='completed',fps=24,frames=[dict(image=str(raw),source_time=.5)],params=dict(seed=987))
    request=dict(folder=str(folder),model='fixture',root=str(tmp_path),model_sha256=digest(model),data=data,
        source_manifest=str(tmp_path/'video.json'),assets=[dict(path=str(raw),sha256=digest(raw))])
    def cutout(im,*args,**kwargs):
        rgba=im.convert('RGBA');mask=Image.new('L',rgba.size);mask.paste(255,(5,5,26,43));rgba.putalpha(mask);return rgba
    with patch('aipictures.background.MODEL'),patch('aipictures.background.MODEL_ROOT'),patch('aipictures.background.model_file',return_value=model),patch('aipictures.background.foreground_rgba',side_effect=cutout):run(request)
    result=json.loads((folder/'result.json').read_text('utf-8'));manifest=Path(result['manifest'])
    data,paths=read_source(manifest);_,originals=read_source(manifest,original=True)
    assert originals==[raw] and data['export_background']['rgb_preserved']
    with Image.open(paths[0]) as im,Image.open(raw) as source:
        assert im.getchannel('A').getextrema()==(0,255) and im.size==source.size
        assert im.convert('RGB').tobytes()==source.tobytes()
    assert raw.read_bytes()==before
    for transparent in (True,False):
        target=tmp_path/('alpha.png' if transparent else 'raw.png')
        export_selection(manifest,[0],tmp_path/('alpha' if transparent else 'opaque'),target,'sheet',8,1,transparent,True,threading.Event(),lambda *_:None)
        with Image.open(target) as im:assert im.getchannel('A').getextrema()==((0,255) if transparent else (255,255))
    assert raw.read_bytes()==before

def test_cancel_before_export_does_not_extract_or_load_model(tmp_path):
    cancel=threading.Event();cancel.set()
    with patch('aipictures.video_io.prepare_export_frames') as extract,pytest.raises(Cancelled):prepare(tmp_path/'video.json',cancel,lambda *_:None)
    extract.assert_not_called()
