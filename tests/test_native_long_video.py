import json
import threading
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from aipictures.native_long_video import plan,generate,segment_prompt
from aipictures.video_script import simple,prompt
from aipictures.storage import write_json
from aipictures.video_audio import package,read_audio,save_wav
from tests.test_short_video import picture_source


@pytest.mark.parametrize('seconds',[9,10,15,16,23,30,31,35,40,45])
def test_native_plan_keeps_bounded_working_set_and_exact_output(seconds):
    parts=plan(seconds)
    assert len(parts)<=8 and all(p['frames']<=192 for p in parts)
    assert parts[0]['frames']==parts[0]['new_frames']
    assert all(p['frames']-p['new_frames']==22 for p in parts[1:])
    assert parts[-1]['end']==seconds
    assert sum(p['new_frames'] for p in parts)>=seconds*24
    assert sum(p['new_frames'] for p in parts)-seconds*24<17
    assert all(b['start_frame']==a['start_frame']+a['new_frames'] for a,b in zip(parts,parts[1:]))


@pytest.mark.parametrize('value',[8,46,30.5,float('nan')])
def test_invalid_long_requests_stop_before_generation(value):
    with pytest.raises(ValueError):plan(value)


def test_context_chain_retains_own_audio_and_continues_from_previous_video(tmp_path):
    params=dict(seconds=30,seed=1,h3_settings={},short_script=simple('船缓慢前进，水声和钢琴配乐',30))
    params['prompt']=prompt(params['short_script']);calls=[]
    def backend(folder,request,cancel,emit):
        calls.append(request);frames=request['h3_frames']-(22 if request.get('h3_continue_video') else 0)
        rgb=folder/'rgb.npy';np.save(rgb,np.full((frames,2,2,3),len(calls),np.uint8))
        video=folder/'clip.mp4';video.write_bytes(str(len(calls)).encode())
        return dict(video=str(video),native_rgb=str(rgb))
    target=tmp_path/'joined.mp4';target.write_bytes(b'joined-fixture')
    with patch('aipictures.h3_backend.generate',side_effect=backend),patch('aipictures.native_long_worker.join',return_value=target):
        result=generate(tmp_path,params,threading.Event(),lambda *_:None)
        assert len(calls)==5 and all(p['h3_two_pass'] for p in calls)
        assert all('h3_continue_video' in p and p['h3_continue_sha256'] for p in calls[1:])
        array=np.load(result['native_rgb']);assert array.shape==(720,2,2,3)
        assert array[0,0,0,0]==1 and array[-1,0,0,0]==5
        stamp=Path(result['native_rgb']).stat().st_mtime_ns
        generate(tmp_path,dict(params,resume_chain=True),threading.Event(),lambda *_:None)
        assert len(calls)==5 and Path(result['native_rgb']).stat().st_mtime_ns==stamp
    state=json.loads((tmp_path/'native-chain.json').read_text('utf-8'))
    assert not state['video_blending'] and state['context_frames']==22


def test_explicit_resume_preserves_failed_attempt_and_reuses_finished_parts(tmp_path):
    params=dict(seconds=9,seed=8,h3_settings={},short_script=simple('船缓慢前行',9))
    params['prompt']=prompt(params['short_script']);calls=[];failed=False
    def backend(folder,request,cancel,emit):
        nonlocal failed
        calls.append(folder.name)
        if request.get('h3_continue_video') and not failed:
            failed=True;(folder/'failure.log').write_text('preserve this incomplete attempt')
            raise ValueError('interrupted')
        frames=request['h3_frames']-(22 if request.get('h3_continue_video') else 0)
        rgb=folder/'rgb.npy';np.save(rgb,np.full((frames,2,2,3),request['seed'],np.uint8))
        video=folder/'clip.mp4';video.write_bytes(str(request['seed']).encode())
        return dict(video=str(video),native_rgb=str(rgb))
    target=tmp_path/'joined.mp4';target.write_bytes(b'joined')
    with patch('aipictures.h3_backend.generate',side_effect=backend),patch('aipictures.native_long_worker.join',return_value=target):
        with pytest.raises(ValueError,match='interrupted'):generate(tmp_path,params,threading.Event(),lambda *_:None)
        with pytest.raises(ValueError):generate(tmp_path,params,threading.Event(),lambda *_:None)
        result=generate(tmp_path,dict(params,resume_chain=True),threading.Event(),lambda *_:None)
    assert calls==['01','02','02_attempt_02']
    assert (tmp_path/'native_segments/02/failure.log').read_text()=='preserve this incomplete attempt'
    assert len(np.load(result['native_rgb']))==216


def test_modified_completed_raw_frame_data_blocks_resume(tmp_path):
    params=dict(seconds=9,seed=8,h3_settings={},short_script=simple('船缓慢前行',9))
    params['prompt']=prompt(params['short_script'])
    def backend(folder,request,cancel,emit):
        frames=request['h3_frames']-(22 if request.get('h3_continue_video') else 0)
        rgb=folder/'rgb.npy';np.save(rgb,np.zeros((frames,2,2,3),np.uint8))
        video=folder/'clip.mp4';video.write_bytes(b'clip')
        return dict(video=str(video),native_rgb=str(rgb))
    target=tmp_path/'joined.mp4';target.write_bytes(b'joined')
    with patch('aipictures.h3_backend.generate',side_effect=backend),patch('aipictures.native_long_worker.join',return_value=target):
        generate(tmp_path,params,threading.Event(),lambda *_:None)
        raw=tmp_path/'native_segments/01/rgb.npy';value=np.load(raw);value[0]=255;np.save(raw,value)
        with pytest.raises(ValueError,match='原始画面变化'):
            generate(tmp_path,dict(params,resume_chain=True),threading.Event(),lambda *_:None)


def test_long_script_is_localized_to_the_requested_shot():
    script=simple('蓝色机器人',30);script['shots']=[dict(start=0,end=15,visual='慢慢举手',camera='固定机位',sound='钢琴'),dict(start=15,end=30,visual='缓慢放下手',camera='固定机位',sound='钢琴继续')]
    value=segment_prompt(dict(short_script=script,prompt=prompt(script)),plan(30)[3])
    assert '缓慢放下手' in value and '慢慢举手' not in value
    assert '0.000' in value and '承接已有音画上下文' in value


def test_native_audio_delivery_never_synthesizes_a_replacement(tmp_path):
    picture_source(tmp_path);artifacts=tmp_path/'animation.artifacts';artifacts.mkdir()
    t=np.arange(32000)/32000;values=np.tile(.2*np.sin(2*np.pi*220*t),(2,1)).astype('float32');np.save(artifacts/'audio.npy',values)
    with patch('aipictures.video_audio.compose_music',side_effect=AssertionError('No synth in native mode')):
        result=package(tmp_path,None,1,dict(audio_mode='h3_native',seed=1),threading.Event())
    assert result['music_source']=='h3_native' and result['music'] is None
    assert read_audio(result['audio'],1).shape==(2,48000)
