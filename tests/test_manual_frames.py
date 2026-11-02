import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from aipictures.engine import Cancelled
from aipictures.selected_frames import export_selection
from aipictures.video_generation import generation_prompt


def fixture(folder):
    folder.mkdir();rows=[]
    for i in range(9):
        image=Image.new('RGBA',(32,48),(40,90+i,150,0));image.paste((240,240,230,255),(8,8,22,40))
        image.putpixel((12,20),(20+i,70,150,255));image.save(folder/f'f{i}.png');rows.append({'image':f'f{i}.png'})
    from aipictures.video_io import encode_pngs
    video=folder/'source.mp4';encode_pngs([folder/row['image'] for row in rows],video,24,threading.Event())
    manifest=folder/'video.json';manifest.write_text(json.dumps({'status':'completed','source_video':str(video),'fps':24,'frames':rows,'params':{'seed':987654321}}))
    return manifest


def test_manual_noncontiguous_frames_sheet_readback_and_seed(tmp_path):
    manifest=fixture(tmp_path/'source');out=tmp_path/'sheet.png'
    result=export_selection(manifest,[7,2,5],tmp_path/'cache',out,'sheet',12,2,False,True,threading.Event(),lambda *_:None)
    meta=json.loads(out.with_suffix('.json').read_text())
    assert meta['source_indices']==[2,5,7] and meta['seed']==987654321 and meta['fps']==12
    with Image.open(out) as sheet:
        assert sheet.text['Seed']=='987654321'
        for row,index in zip(meta['frames'],[2,5,7]):
            r=row['rect']
            with Image.open(manifest.parent/f'f{index}.png') as original:
                assert sheet.crop((r['x'],r['y'],r['x']+r['w'],r['y']+r['h'])).tobytes()==original.tobytes()
    record=json.loads(Path(result['manifest']).read_text())
    assert record['method']=='manual_video_frames' and not record['temporal_blending'] and not record['content_scaled']


def test_individual_pngs_export_only_checked_frames_and_no_overwrites(tmp_path):
    manifest=fixture(tmp_path/'source');target=tmp_path/'exports';target.mkdir()
    (target/'frame_000.png').write_bytes(b'user-file')
    result=export_selection(manifest,[8,0],tmp_path/'cache',target,'pngs',8,4,False,True,threading.Event(),lambda *_:None)
    exported=Path(result['output']);assert len(list(exported.glob('*.png')))==2
    assert (target/'frame_000.png').read_bytes()==b'user-file'
    for i,source in enumerate([0,8]):
        with Image.open(exported/f'frame_{i:03d}.png') as frame,Image.open(manifest.parent/f'f{source}.png') as original:
            assert frame.tobytes()==original.tobytes() and frame.text['Seed']=='987654321'
    assert json.loads((exported/'animation.json').read_text())['source_indices']==[0,8]


def test_cancel_or_empty_selection_never_publishes_asset(tmp_path):
    manifest=fixture(tmp_path/'source');cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):export_selection(manifest,[0],tmp_path/'cancelled',tmp_path/'out.png','sheet',8,1,False,True,cancel,lambda *_:None)
    assert not (tmp_path/'out.png').exists()
    with pytest.raises(ValueError,match='至少选取'):export_selection(manifest,[],tmp_path/'empty',tmp_path/'out.png','sheet',8,1,False,True,threading.Event(),lambda *_:None)
    assert not (tmp_path/'empty').exists()


def test_one_positive_prompt_no_hidden_action_override():
    params={'prompt_layout':'unified','prompt':'参考角色换成正面，抬起右手挥动，然后放下。','action_description':'跑步'}
    text=generation_prompt(params,True)
    assert params['prompt'] in text and '跑步' not in text and '优先执行的动作要求' not in text


def test_switching_export_format_reuses_identical_processed_colors(tmp_path):
    manifest=fixture(tmp_path/'source');selected=[0,3]
    with patch('aipictures.background.foreground_rgba',side_effect=lambda image,*a,**k:image.copy()) as matte:
        result=export_selection(manifest,selected,tmp_path/'first',tmp_path/'sheet.png','sheet',8,2,True,True,threading.Event(),lambda *_:None)
        assert matte.call_count==2
    exports=tmp_path/'exports';exports.mkdir()
    prepared={index:Path(result['manifest']).parent/f'frame_{i:03d}.png' for i,index in enumerate(selected)}
    with patch('aipictures.background.foreground_rgba') as matte:
        second=export_selection(manifest,selected,tmp_path/'second',exports,'pngs',8,2,True,True,threading.Event(),lambda *_:None,prepared=prepared)
        matte.assert_not_called()
    assert json.loads(Path(second['manifest']).read_text())['reused_processed_frames']==selected


def test_actual_qt_selection_and_seed_controls():
    r=subprocess.run([sys.executable,'-m','tests.live_manual_frames'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONUTF8='1'),capture_output=True,timeout=40)
    assert r.returncode==0,r.stdout.decode('utf-8','replace')+r.stderr.decode('utf-8','replace')
