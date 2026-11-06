"""Export choices defer derived files without changing the original RGB pixels."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch
import av
import numpy as np
import pytest
from PIL import Image
from aipictures.engine import Cancelled
from aipictures.video_generation import generate
from aipictures.video_io import encode_native_rgb,native_rgb_image,prepare_export_frames


def deferred(folder: Path):
    folder.mkdir()
    array=np.random.default_rng(17).integers(0,256,(9,32,48,3),dtype=np.uint8)
    rgb=folder/'rgb.npy';np.save(rgb,array,allow_pickle=False)
    delivery=folder/'delivery.mp4';delivery.write_bytes(b'preserved-delivery')
    with patch('aipictures.h3_backend.generate',return_value=dict(video=str(delivery),native_rgb=str(rgb))), \
         patch('aipictures.video_io.native_rgb_frames',side_effect=AssertionError('Eager PNG extraction')), \
         patch('aipictures.video_io.encode_pngs',side_effect=AssertionError('Eager video re-encoding')):
        result=generate(None,folder,dict(engine='h3',seconds=4,defer_exports=True),threading.Event(),lambda *_:None)
    return Path(result['manifest']),array


def test_generation_finishes_without_pngs_and_preview_uses_exact_rgb(tmp_path):
    manifest,array=deferred(tmp_path/'job');data=json.loads(manifest.read_text('utf-8'))
    assert data['status']=='completed' and data['frames']==[] and data['frame_count']==9
    assert not list(manifest.parent.rglob('*.png'))
    np.testing.assert_array_equal(np.asarray(native_rgb_image(Path(data['native_rgb_source']),8)),array[8])


def test_video_export_does_not_require_pngs_and_is_lossless(tmp_path):
    manifest,array=deferred(tmp_path/'job');out=tmp_path/'export.mp4'
    encode_native_rgb(manifest.parent/'rgb.npy',out,24,threading.Event(),lambda *_:None)
    with av.open(str(out)) as container:
        actual=np.stack([f.to_ndarray(format='rgb24') for f in container.decode(video=0)])
    np.testing.assert_array_equal(actual,array)
    assert not list(manifest.parent.rglob('*.png'))


def test_model_alignment_tail_is_excluded_without_changing_original_rgb(tmp_path):
    folder=tmp_path/'job';folder.mkdir()
    array=np.random.default_rng(21).integers(0,256,(107,16,24,3),dtype=np.uint8)
    rgb=folder/'rgb.npy';np.save(rgb,array,allow_pickle=False)
    delivery=folder/'delivery.mp4';delivery.write_bytes(b'original-delivery')
    with patch('aipictures.h3_backend.generate',return_value=dict(video=str(delivery),native_rgb=str(rgb))):
        result=generate(None,folder,dict(engine='h3',seconds=4,defer_exports=True),threading.Event(),lambda *_:None)
    manifest=Path(result['manifest']);data=json.loads(manifest.read_text('utf-8'))
    assert data['frame_count']==96 and data['model_frame_count']==107 and data['duration_seconds']==4
    target=tmp_path/'export.mp4'
    encode_native_rgb(rgb,target,24,threading.Event(),lambda *_:None,frame_count=data['frame_count'])
    with av.open(str(target)) as container:
        actual=np.stack([f.to_ndarray(format='rgb24') for f in container.decode(video=0)])
    np.testing.assert_array_equal(actual,array[:96])
    prepare_export_frames(manifest,threading.Event(),lambda *_:None)
    assert len(json.loads(manifest.read_text('utf-8'))['frames'])==96
    assert np.load(rgb,mmap_mode='r',allow_pickle=False).shape[0]==107


def test_frame_export_is_explicit_cached_and_keeps_source_colors(tmp_path):
    manifest,array=deferred(tmp_path/'job');before=(manifest.parent/'rgb.npy').read_bytes()
    prepare_export_frames(manifest,threading.Event(),lambda *_:None)
    data=json.loads(manifest.read_text('utf-8'));assert len(data['frames'])==9
    for i,row in enumerate(data['frames']):
        with Image.open(manifest.parent/row['image']) as image:np.testing.assert_array_equal(np.asarray(image),array[i])
    prepare_export_frames(manifest,threading.Event(),lambda *_:None)
    assert len(list(manifest.parent.glob('export_frames_*')))==1
    assert (manifest.parent/'rgb.npy').read_bytes()==before


def test_cancel_export_keeps_completed_animation_and_no_published_partial(tmp_path):
    manifest,_=deferred(tmp_path/'job');before=manifest.read_bytes();cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):prepare_export_frames(manifest,cancel,lambda *_:None)
    assert manifest.read_bytes()==before
    out=tmp_path/'cancelled.mp4'
    with pytest.raises(Cancelled):encode_native_rgb(manifest.parent/'rgb.npy',out,24,cancel,lambda *_:None)
    assert not out.exists()


def test_actual_qt_lazy_preview_and_both_export_choices():
    result=subprocess.run([sys.executable,'-m','tools.verify_deferred_video'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=40)
    assert result.returncode==0,(result.stdout+result.stderr).decode('utf-8','replace')
