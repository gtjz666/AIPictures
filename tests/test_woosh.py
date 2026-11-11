import json
import threading
from unittest.mock import Mock,patch
import pytest
from aipictures.audio_routing import resolve_kind
from aipictures.sfx_prompt import organize
from aipictures.woosh_generation import generate
from aipictures.audio_prompt import fingerprint
from aipictures.engine import Cancelled


@pytest.mark.parametrize('brief,kind',[
    ('压迫感的史诗配乐，不要音效','music'),('金属剑碰撞的音效，不要背景音乐','sfx'),
    ('舒缓钢琴音乐','music'),('一次短促的爆炸声','sfx'),('Footsteps on stone, no music','sfx'),
    ('A battle soundtrack without sound effects','music')])
def test_route_keeps_exclusions_out_of_engine_selection(brief,kind):assert resolve_kind(brief)==kind


@pytest.mark.parametrize('brief',['史诗背景音乐，无音效和人声','音乐配乐，没有音效','背景音乐，无需音效'])
def test_chinese_absence_is_not_a_sound_effect_request(brief):assert resolve_kind(brief)=='music'


def test_explicit_purpose_overrides_auto_detection():assert resolve_kind('剑的史诗配乐','sfx')=='sfx'


def test_sound_effect_does_not_become_a_musical_arrangement(tmp_path):
    session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    session.complete.return_value=(json.dumps(dict(caption='Two crisp metallic sword impacts, followed by a brief ringing decay. No music.')),dict())
    source='两次清脆的金属刀剑碰撞，然后短促回响，不要音乐'
    result=organize({},source,3,tmp_path/'prompt',threading.Event(),lambda *_:None,session_factory=lambda *_:session)
    assert result['positive_prompt']==source and result['negative_prompt']=='' and session.complete.call_count==1
    assert result['caption_fingerprint']==fingerprint(source,'') and result['kind']=='sfx'
    assert source in session.complete.call_args.args[0][-1]['content']


def test_sfx_cancel_does_not_start_a_model(tmp_path):
    event=threading.Event();event.set()
    with patch('aipictures.woosh_generation.subprocess.Popen') as process,pytest.raises(Cancelled):
        generate(tmp_path,dict(audio_settings={},seconds=3,prompt='impact',seed=4),event,lambda *_:None)
    process.assert_not_called()


@pytest.mark.parametrize('seconds',[0,.1,6,20,float('nan')])
def test_invalid_sfx_duration_fails_before_loading(tmp_path,seconds):
    with patch('aipictures.woosh_generation.subprocess.Popen') as process,pytest.raises(ValueError):
        generate(tmp_path,dict(audio_settings={},seconds=seconds,prompt='impact',seed=4),threading.Event(),lambda *_:None)
    process.assert_not_called()


def test_completed_sfx_is_never_replaced(tmp_path):
    file=tmp_path/'audio.json';file.write_text('{"status":"completed"}','utf-8');original=file.read_bytes()
    with pytest.raises(ValueError,match='重复'):
        generate(tmp_path,dict(audio_settings={},seconds=3,prompt='impact',seed=4),threading.Event(),lambda *_:None)
    assert file.read_bytes()==original
