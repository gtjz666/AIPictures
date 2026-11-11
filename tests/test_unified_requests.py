import json
import threading
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
import pytest
import os
import subprocess
import sys
from aipictures.professional_prompt import organize,style_transfer
from aipictures.manual_video import generate
from aipictures.workflow_library import digest


def test_single_requirement_native_ui_all_categories():
    run=subprocess.run([sys.executable,'-m','tools.verify_single_requirement'],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=60)
    assert run.returncode==0,(run.stdout+run.stderr).decode('utf-8','replace')


def test_reference_edit_keeps_original_instruction_without_visual_analysis_or_recaptioning(tmp_path):
    refs={1:tmp_path/'one.png',2:tmp_path/'two.png'}
    for p in refs.values():p.write_bytes(b'Not decoded or sent as pixels to the language model')
    session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    session.complete.return_value=(json.dumps(dict(positive_prompt='Keep the subject and pose in Image 1; apply only the style from Image 2.',negative_prompt='')), {})
    request='将图一的人物美术风格修改为图二的美术风格，保留图一的人物动作与人物外形'
    with patch('aipictures.intent_observation.observe',side_effect=AssertionError('No visual analysis')):
        result=organize({},request,'',refs,None,tmp_path/'prepared',threading.Event(),lambda *_:None,session_factory=lambda *_:session)
    assert session.complete.call_count==1  # Translation only, no joint-image caption.
    assert '不' not in result['plan']['negative_prompt'] and result['plan']['negative_prompt']==''
    assert request in result['plan']['positive_prompt'] and '不得用图2的人物身份' in result['plan']['positive_prompt']
    assert result['images_read'] is False and not result['observations']
    assert 'image_url' not in json.dumps(session.complete.call_args.args)


def test_reference_motion_uses_direct_generation_inputs_without_starting_a_language_model(tmp_path):
    ref=tmp_path/'one.png';ref.write_bytes(b'Original pixels stay generation-only')
    source=tmp_path/'source.gif';source.write_bytes(b'video guide')
    with patch('aipictures.professional_prompt.TextSession',side_effect=AssertionError('Unnecessary model load')):
        result=organize({},'将图1的人物替换到参考动画中，保持动作','',{1:ref},source,tmp_path/'prepared',threading.Event(),lambda *_:None,selected_kind='animation')
    assert '将图1的人物替换' in result['plan']['positive_prompt'] and result['route']=='h3_reference'
    assert result['plan']['timeline']==[] and result['plan']['negative_prompt']==''


def test_missing_image_is_rejected_before_loading_a_model(tmp_path):
    with patch('aipictures.professional_prompt.TextSession') as load,pytest.raises(ValueError,match='图2'):
        organize({},'采用图2风格','',{},None,tmp_path/'plan',threading.Event(),lambda *_:None)
    load.assert_not_called()


def test_english_reference_instruction_does_not_load_an_unnecessary_translator(tmp_path):
    ref=tmp_path/'one.png';ref.write_bytes(b'Original reference')
    with patch('aipictures.professional_prompt.TextSession',side_effect=AssertionError('No translation needed')):
        value=organize({},'Change the pose in Image 1; preserve the character design.','',{1:ref},None,tmp_path/'plan',threading.Event(),lambda *_:None)
    assert 'preserve the character design' in value['english']['positive'] and not value['images_read']


def test_new_segment_is_one_backend_call_and_preserves_all_delivered_previous_pixels(tmp_path,monkeypatch):
    import aipictures.h3_backend as backend
    import aipictures.video_io as video_io
    import aipictures.video_audio as video_audio
    import aipictures.native_long_worker as joiner
    calls=[]
    def render(folder,params,*_):
        calls.append(params);frames=params['h3_frames']-(22 if params.get('h3_continue_video') else 0)
        rgb=np.full((frames,8,8,3),len(calls)*40,np.uint8);np.save(folder/'native.npy',rgb)
        (folder/'video.mp4').write_bytes(b'new native video')
        return dict(video=str(folder/'video.mp4'),native_rgb=str(folder/'native.npy'))
    def encode(source,target,*_,**kwargs):Path(target).write_bytes(b'silent');assert kwargs['frame_count']==48
    def package(folder,source,seconds,params,cancel):
        assert seconds==2
        (folder/'packaged.mp4').write_bytes(b'new exact two seconds')
        return dict(video=str(folder/'packaged.mp4'))
    def join(folder,params,results,*_):
        assert len(results)==len(calls) and params['seconds']==2*len(calls)
        (folder/'joined.mp4').write_bytes(b'joined');return folder/'joined.mp4'
    monkeypatch.setattr(backend,'generate',render);monkeypatch.setattr(video_io,'encode_native_rgb',encode)
    monkeypatch.setattr(video_audio,'package',package);monkeypatch.setattr(joiner,'join',join)
    first=tmp_path/'first';first.mkdir();params=dict(seconds=2,seed=4,prompt='第一段',audio_mode='h3_native')
    a=generate(first,params,threading.Event(),lambda *_:None)
    manifest=first/'video.json';manifest.write_text(json.dumps(dict(status='completed',native_rgb_source=a['native_rgb'],source_video=a['video'],frame_count=48,fps=24,source_sha256=digest(Path(a['video'])))),'utf-8')
    second=tmp_path/'second';second.mkdir()
    b=generate(second,dict(params,prompt='第二段新要求',continue_from=str(manifest),continue_manifest_sha256=digest(manifest)),threading.Event(),lambda *_:None)
    old=np.load(a['native_rgb']);combined=np.load(b['native_rgb'])
    assert len(calls)==2 and b['frame_count']==96 and np.array_equal(old,combined[:48])
    assert calls[1]['prompt']=='第二段新要求' and Path(calls[1]['h3_continue_video']).parts[-2:]==('previous','video.mp4')
    assert len(np.load(second/'previous/rgb.npy'))==48
    with pytest.raises(ValueError,match='重复'):
        generate(second,params,threading.Event(),lambda *_:None)


def test_native_progress_finishes_its_busy_animation():
    from aipictures.task_display import TaskDisplay
    from PySide6.QtWidgets import QWidget,QApplication
    app=QApplication.instance() or QApplication([])
    parent=QWidget();progress=TaskDisplay(parent);progress.start();progress.progress.setRange(0,0)
    progress.finish('completed')
    assert progress.progress.maximum()==100 and progress.progress.value()==100 and not progress.clock.isActive()
    parent.close()
