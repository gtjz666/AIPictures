"""Real CPU media round trips and storyboard boundaries, with no model downloads."""
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

from aipictures.engine import Cancelled
from aipictures.video_audio import compose_music,mux,package,read_audio,save_wav,separate
from aipictures.video_generation import generate,generation_prompt
from aipictures.video_io import encode_native_rgb
from aipictures.video_script import simple,validate,prompt,organize


def picture_source(root,count=24):
    rng=np.random.default_rng(2)
    array=rng.integers(0,256,(count,32,48,3),dtype=np.uint8)
    rgb=root/'rgb.npy';np.save(rgb,array)
    video=root/'video_silent.mp4'
    encode_native_rgb(rgb,video,24,threading.Event(),lambda *_:None,frame_count=count)
    return rgb,video,array


def decode(path):
    with av.open(str(path)) as c:return np.stack([f.to_ndarray(format='rgb24') for f in c.decode(video=0)])


@pytest.mark.parametrize('style',['gentle','bright','dramatic'])
def test_original_score_is_audible_stereo_and_exact_length(style):
    music=compose_music(2,style,42)
    assert music.shape==(2,96000) and np.isfinite(music).all()
    assert .01<float(np.sqrt(np.mean(music**2)))<.7
    assert np.max(np.abs(music))<=.701 and not np.array_equal(music[0],music[1])


def test_real_mux_and_separation_preserve_all_picture_pixels(tmp_path):
    _,silent,rgb=picture_source(tmp_path)
    music=compose_music(1,'bright',123);target=tmp_path/'combined.mp4';cancel=threading.Event()
    mux(silent,music,target,cancel)
    with av.open(str(target)) as c:
        assert len(c.streams.audio)==len(c.streams.video)==1
        assert c.streams.audio[0].sample_rate==48000
        assert abs(float(c.streams.video[0].duration*c.streams.video[0].time_base)-1)<.001
    np.testing.assert_array_equal(decode(target),rgb)
    picture=tmp_path/'separated.mp4';sound=tmp_path/'separated.wav'
    separate(target,picture,sound,cancel)
    np.testing.assert_array_equal(decode(picture),rgb)
    with av.open(str(picture)) as c:assert not c.streams.audio
    actual=read_audio(sound,1)
    assert actual.shape==music.shape and float(np.sqrt(np.mean(actual**2)))>.01
    assert np.corrcoef(actual.flatten(),music.flatten())[0,1]>.95


def test_package_retains_native_sound_and_independent_looped_music(tmp_path):
    _,silent,rgb=picture_source(tmp_path)
    artifacts=tmp_path/'animation.artifacts';artifacts.mkdir()
    t=np.arange(64000)/32000;native=np.tile((.15*np.sin(2*np.pi*300*t)),(2,1)).astype('float32')
    np.save(artifacts/'audio.npy',native)
    imported=tmp_path/'input.wav';save_wav(imported,compose_music(.25,'gentle',5))
    data=package(tmp_path,None,1,dict(seed=5,music_file=str(imported)),threading.Event())
    assert data['native_audio_present'] and data['music_source']=='imported'
    for key in ('video','audio','music','native_audio','silent_video'):assert Path(data[key]).is_file()
    assert read_audio(data['music'],1).shape==(2,48000)
    np.testing.assert_array_equal(decode(data['video']),rgb)
    with av.open(data['native_audio']) as c:assert abs(c.duration/av.time_base-1)<.01


def test_cancelled_mux_does_not_replace_existing_output(tmp_path):
    _,source,_=picture_source(tmp_path)
    target=tmp_path/'saved.mp4';target.write_bytes(b'existing user export')
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):mux(source,compose_music(1,'gentle',1),target,cancel)
    assert target.read_bytes()==b'existing user export'
    assert not list(tmp_path.glob('*.part.mp4'))


def test_invalid_script_is_rejected_before_loading_video_model(tmp_path):
    params=dict(creation_kind='short_video',engine='h3',seconds=4,short_script=simple('小船',8))
    with patch('aipictures.h3_backend.generate') as backend,pytest.raises(ValueError):
        generate(None,tmp_path,params,threading.Event(),lambda *_:None)
    backend.assert_not_called()
    assert json.loads((tmp_path/'video.json').read_text('utf-8'))['status']=='failed'


def test_cancelled_separation_does_not_replace_exports(tmp_path):
    _,source,_=picture_source(tmp_path);clip=tmp_path/'with_audio.mp4'
    mux(source,compose_music(1,'gentle',8),clip,threading.Event())
    picture=tmp_path/'user.mp4';audio=tmp_path/'user.wav';picture.write_bytes(b'old-video');audio.write_bytes(b'old-audio')
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):separate(clip,picture,audio,cancel)
    assert picture.read_bytes()==b'old-video' and audio.read_bytes()==b'old-audio'
    assert not list(tmp_path.glob('*.part.*'))


def test_generation_integrates_audio_without_automatic_png_or_sprite_exports(tmp_path):
    rgb,_,array=picture_source(tmp_path,count=29)
    params=dict(engine='h3',creation_kind='short_video',seconds=1,seed=3,negative='',prompt='湖面的船缓慢前行',
                prompt_layout='unified',defer_exports=True,music_style='gentle',short_script=simple('湖面的船缓慢前行',1))
    with patch('aipictures.h3_backend.generate',return_value=dict(native_rgb=str(rgb))):
        result=generate(None,tmp_path,params,threading.Event(),lambda *_:None)
    manifest=json.loads(Path(result['manifest']).read_text('utf-8'))
    assert manifest['frame_count']==24 and manifest['alignment_tail_frames']==5
    assert manifest['frame_storage']=='native_rgb' and manifest['frames']==[]
    assert not manifest['video_export_pending'] and manifest['music_source']=='original_local_score'
    assert not manifest['native_audio_present'] and not manifest['sprites_created']
    np.testing.assert_array_equal(decode(result['video']),array[:24])
    assert '不切镜' not in generation_prompt(params,False)


@pytest.mark.parametrize('changes',[
    dict(shots=[dict(start=0,end=5,visual='船',camera='平移',sound='水声')]),
    dict(shots=[dict(start=.1,end=4,visual='船',camera='平移',sound='水声')]),
    dict(shots=[dict(start=0,end=2,visual='船',camera='平移',sound='水声')]),
    dict(duration_seconds=6),dict(shots=['bad']),dict(music_style='unknown')])
def test_script_rejects_inconsistent_timing(changes):
    with pytest.raises(ValueError):validate(dict(simple('小船',4),**changes),4)


def test_script_uses_one_session_and_never_analyzes_motion(tmp_path):
    calls=[];cancel=threading.Event()
    class Session:
        def __init__(self,*_):calls.append('start')
        def __enter__(self):return self
        def __exit__(self,*_):calls.append('exit')
        def complete(self,messages,**kwargs):
            calls.append(messages)
            assert len(messages[1]['content'])==1 and '不猜视频内容' in messages[0]['content']
            value=simple('小船在清晨湖面前进',4);value['negative_prompt']=''
            value.pop('version');value.pop('duration_seconds');value.pop('music_style')
            return json.dumps(value,ensure_ascii=False),{}
    result=organize({},'小船前进',4,'gentle',None,tmp_path/'script',cancel,lambda *_:None,session_factory=Session)
    assert calls[0]=='start' and calls[-1]=='exit' and len(calls)==3
    assert '0.000–4.000秒' in prompt(result) and result['negative_prompt']
    assert (tmp_path/'script/script.md').is_file()


def test_native_qt_short_composer_and_av_exports():
    result=subprocess.run([sys.executable,'-m','tools.verify_short_video_ui'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=60)
    assert result.returncode==0,(result.stdout+result.stderr).decode('utf-8','replace')
