import io
import json
import threading
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
import pytest
from aipictures.audio_duration import finish,render_seconds
from aipictures.audio_prompt import organize,fingerprint,TextSession
from aipictures.video_audio import save_wav
from aipictures.audio_generation import generate


def test_audio_prompt_native_qt_workflow():
    result=subprocess.run([sys.executable,'-m','tools.verify_audio_prompts'],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=60)
    assert result.returncode==0,(result.stdout+result.stderr).decode('utf-8','replace')


def music(path,seconds,active_seconds):
    t=np.arange(round(seconds*48000))/48000
    v=.2*np.sin(2*np.pi*220*t);v[t>=active_seconds]=.0004*np.sin(2*np.pi*110*t[t>=active_seconds])
    save_wav(path,np.stack([v,v]));return v


def test_silent_tail_is_not_successful_twenty_second_music(tmp_path):
    path=tmp_path/'master.wav';music(path,20,16.5)
    with pytest.raises(ValueError,match='有效音乐约16.5秒'):finish(path,20)
    assert path.is_file()


def test_full_music_keeps_natural_ending_without_padding_looping_or_tempo_change(tmp_path):
    path=tmp_path/'master.wav';original=music(path,29,24)
    audio,report=finish(path,20)
    assert audio.shape==(2,960000) and report['crop_start_seconds']>0
    assert np.sqrt(np.mean(audio[:,-48000:]**2))>.05 and audio[:,-1].max()==0
    assert not report['silence_padded'] and not report['looped'] and not report['tempo_changed']
    start=round(report['crop_start_seconds']*48000)
    assert np.allclose(audio[0,4800:9600],original[start+4800:start+9600],atol=.00004)


def test_short_master_rejected_instead_of_silence_padding(tmp_path):
    path=tmp_path/'short.wav';music(path,16,16)
    with pytest.raises(ValueError,match='不足所选时长'):finish(path,20)
    assert render_seconds(20)==29


def test_organizer_one_text_session_no_music_and_bilingual_exclusions(tmp_path):
    value=dict(positive_prompt='压迫感的史诗管弦配乐，低音弦乐与铜管逐层推进。',negative_prompt='不要人声。底噪、爆音。',english_caption='Epic orchestral instrumental with growing tension, clear strings and brass.',english_avoid='Voices, background noise, clipping.',english_requirement='Oppressive epic instrumental music, building in layers.')
    session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    session.complete.return_value=(json.dumps(value,ensure_ascii=False),{})
    factory=Mock(return_value=session)
    result=organize({'test':True},'压迫感，层层推进',20,tmp_path/'plan',threading.Event(),lambda *_:None,exclusions='不要人声。',session_factory=factory)
    factory.assert_called_once();session.complete.assert_called_once()
    assert result['caption_fingerprint']==fingerprint(result['positive_prompt'],result['negative_prompt'])
    assert result['positive_prompt'].startswith('压迫感，层层推进') and result['english_caption'].startswith('Oppressive')
    assert json.loads((tmp_path/'plan/request.json').read_text('utf-8'))['seconds']==20


def test_paraphrased_negative_keeps_original_manual_words_and_submitted_exclusions(tmp_path):
    session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    session.complete.return_value=(json.dumps(dict(positive_prompt='史诗配乐',negative_prompt='电吉他、底噪',english_caption='Epic music',english_avoid='Electric guitar, noise',english_requirement='Epic music')), {})
    result=organize({'test':True},'史诗配乐',20,tmp_path/'plan',threading.Event(),lambda *_:None,exclusions='不要电吉他',session_factory=lambda *_:session)
    assert '不要电吉他' in result['negative_prompt'] and 'Electric guitar' in result['english_caption']


def test_audio_prompt_does_not_load_a_visual_projector():
    config=dict(server='server',model='model',projector='projector',context=8192,audio_prompt_cpu=True)
    command=TextSession(config,None,None,None).command(1234)
    assert '--mmproj' not in command and '--image-max-tokens' not in command
    assert command[command.index('-ngl')+1]=='0' and command[command.index('--device')+1]=='none'


@pytest.mark.parametrize('edited',[False,True])
def test_audio_submission_reuses_matching_english_and_translates_only_manual_changes(tmp_path,monkeypatch,edited):
    from aipictures import audio_generation as module
    from aipictures import audio_prompt
    old='史诗配乐';positive='改用小提琴独奏' if edited else old;negative='不要人声'
    params=dict(prompt=positive,negative=negative,seconds=20,seed=4,audio_settings={'python':'fixture'},intent_settings={'fixture':True},
        caption_english='Original epic music; no voices.',caption_fingerprint=fingerprint(old,negative))
    text=Mock();text.__enter__=Mock(return_value=text);text.__exit__=Mock(return_value=False)
    text.complete.return_value=(json.dumps(dict(caption='Edited solo violin, no voices.')), {})
    factory=Mock(return_value=text);monkeypatch.setattr(audio_prompt,'TextSession',factory)
    monkeypatch.setattr('aipictures.motion_native_backend.release_shared',lambda *a,**k:None)
    monkeypatch.setattr('aipictures.owned_process.OwnedProcessJob',lambda *_:SimpleNamespace(close=lambda:None))
    class Worker:
        pid=123;returncode=0
        def __init__(self,command,**kwargs):
            self.stdin=io.BytesIO();music(tmp_path/'audio-master.wav',29,24)
            kwargs['stdout'].write('{"ok":true,"mode":"fixture"}\n');kwargs['stdout'].flush()
        def poll(self):return 0
    monkeypatch.setattr(module.subprocess,'Popen',Worker)
    result=generate(tmp_path,params,threading.Event(),lambda *_:None)
    assert factory.call_count==int(edited)
    request=json.loads((tmp_path/'request.json').read_text('utf-8'))
    assert request['seconds']==29 and request['deliver_seconds']==20
    assert ('Edited solo violin' if edited else 'Original epic music') in request['caption']
    data=json.loads((tmp_path/'audio.json').read_text('utf-8'))
    assert data['status']=='completed' and data['duration_integrity']['target_seconds']==20
    assert data['duration_integrity']['trailing_removed_seconds']>3
