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
from aipictures.audio_prompt import organize,fingerprint,TextSession,SECTIONS,normalize,DEFAULT_AVOID,translate
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


def music_plan(**overrides):
    return dict(musical_intent='压迫感的史诗管弦配乐。',instrumentation='低音弦乐重复动机，铜管主奏，大鼓支撑。',
        rhythm_and_dynamics='稳重节拍，由弱到强，逐步加密。',development='弦乐开场、铜管递进，高潮后自然收束。',
        production='声部分离清晰，保留力度层次。',exclusion_quotes=[])|overrides


def text_session(value,caption='Oppressive epic instrumental music, string ostinato, brass lead and bass drum building to a natural ending. No voices.'):
    session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    session.complete.side_effect=[(json.dumps(value,ensure_ascii=False),{}),(json.dumps(dict(caption=caption,avoid='Unrequested voices, unwanted noise and artifacts.')), {})]
    return session


def test_organizer_one_text_session_no_music_and_bilingual_exclusions(tmp_path):
    value=music_plan()
    session=text_session(value)
    factory=Mock(return_value=session)
    result=organize({'test':True},'压迫感，层层推进',20,tmp_path/'plan',threading.Event(),lambda *_:None,exclusions='不要人声。',session_factory=factory)
    factory.assert_called_once();assert session.complete.call_count==2
    assert result['caption_fingerprint']==fingerprint(result['positive_prompt'],result['negative_prompt'])
    assert result['source_brief']=='压迫感，层层推进'
    assert all(title+'：' in result['positive_prompt'] for _,title in SECTIONS)
    assert not result['positive_prompt'].startswith(result['source_brief']) and '铜管主奏' in result['positive_prompt']
    assert result['english_caption'].startswith('Oppressive') and result['english_caption'].count('Oppressive')==1
    translation=json.loads(session.complete.call_args.args[0][1]['content'])
    assert translation['music']==result['positive_prompt'] and translation['avoid']==result['negative_prompt']
    assert json.loads((tmp_path/'plan/request.json').read_text('utf-8'))['seconds']==20


def test_paraphrased_negative_keeps_original_manual_words_and_submitted_exclusions(tmp_path):
    session=text_session(music_plan(exclusion_quotes=['禁止电吉他']),caption='Epic instrumental. Avoid Electric guitar.')
    result=organize({'test':True},'史诗配乐',20,tmp_path/'plan',threading.Event(),lambda *_:None,exclusions='不要电吉他',session_factory=lambda *_:session)
    assert '不要电吉他' in result['negative_prompt'] and 'Electric guitar' in result['english_caption']


def test_empty_optional_negatives_do_not_discard_a_valid_professional_brief(tmp_path):
    # The user's two actual responses had both empty; the old all-fields check failed.
    session=text_session(music_plan(),caption='Instrumental music. '+DEFAULT_AVOID[1])
    result=organize({'test':True},'我想要舒缓但淡淡悲伤的背景音乐',20,tmp_path/'plan',threading.Event(),lambda *_:None,session_factory=lambda *_:session)
    assert result['negative_prompt']==DEFAULT_AVOID[0] and DEFAULT_AVOID[1] in result['english_caption']
    assert (tmp_path/'plan/result.json').is_file() and result['prompt_policy']=='professional_music_v2'


def test_professional_detail_is_not_replaced_with_near_identical_original_chat():
    value=music_plan();brief=value['musical_intent']+'低音弦乐与铜管。'
    result=normalize(value,brief)
    assert result['positive_prompt']!=brief and result['source_brief']==brief
    assert '重复动机' in result['positive_prompt'] and '逐步加密' in result['positive_prompt']


def test_manual_solo_choices_are_passed_as_priority_without_hidden_orchestration(tmp_path):
    value=music_plan(musical_intent='舒缓悲伤的钢琴独奏。',instrumentation='仅钢琴，右手旋律、左手分解和弦。',
        rhythm_and_dynamics='严格72 BPM，轻柔力度。',development='简短引入、轻微变奏、自然延音结束。',production='保留触键细节，温暖清晰。',
        exclusion_quotes=['不要弦乐和打击乐'])
    session=text_session(value,caption='Soothing, subtly sad solo piano at exactly 72 BPM; right-hand melody over left-hand arpeggios, gentle variation and natural release. No strings or percussion.')
    manual='只要钢琴独奏，72 BPM，不要弦乐和打击乐'
    result=organize({'test':True},'宏大史诗配乐',20,tmp_path/'plan',threading.Event(),lambda *_:None,manual_prompt=manual,session_factory=lambda *_:session)
    payload=json.loads(session.complete.call_args_list[0].args[0][1]['content'])
    assert payload['manual_prompt']==payload['requirement']==manual and result['positive_prompt'].startswith('方向与情绪：舒缓悲伤')
    assert '铜管' not in result['positive_prompt'] and '72 BPM' in result['english_caption']


def test_assistant_cannot_invent_extra_excluded_instruments():
    value=normalize(music_plan(exclusion_quotes=['不要杂音','禁止铜管','禁止电子音色']),'史诗音乐，不要杂音')
    assert value['negative_prompt']=='不要杂音'
    assert value['ignored_exclusion_quotes']==['禁止铜管','禁止电子音色']


def test_empty_model_exclusions_still_preserve_explicit_bans_from_the_actual_brief():
    value=normalize(music_plan(),'宏大史诗配乐，不要杂音，不含人声。')
    assert '不要杂音' in value['negative_prompt'] and '不含人声' in value['negative_prompt']


def test_mixed_language_translation_never_enters_cached_english_caption():
    session=Mock();session.complete.return_value=(json.dumps(dict(caption='Solo piano, no打击乐',avoid='Percussion')), {})
    with pytest.raises(ValueError,match='语言不符'):translate(session,'钢琴独奏','不要打击乐')


def test_real_translation_substitution_is_rejected_and_glossary_contains_only_used_instruments():
    session=Mock();session.complete.return_value=(json.dumps(dict(caption='Piano and double bass with vibraphone and temple blocks',avoid='')), {})
    with pytest.raises(ValueError,match='遗漏指定乐器'):translate(session,'钢琴、大提琴、木琴、铃鼓','')
    payload=json.loads(session.complete.call_args.args[0][1]['content'])
    assert payload['instrument_glossary']==dict(钢琴='piano',大提琴='cello',木琴='xylophone',铃鼓='tambourine')


def test_generated_silent_tail_is_replaced_with_a_musical_release_but_user_silence_is_retained():
    value=music_plan(development='乐器持续至结束，最后1秒静音收尾。')
    assert '静音' not in normalize(value,'舒缓配乐')['positive_prompt']
    assert '最后1秒静音' in normalize(value,'配乐最后1秒静音')['positive_prompt']


def test_unrequested_generated_absolute_seconds_cannot_conflict_with_duration_reserve():
    value=music_plan(rhythm_and_dynamics='60 BPM，音乐持续至20秒结束。',development='开场3秒钢琴引入，中段8秒展开，末段9秒收束。')
    result=normalize(value,'舒缓的悲伤配乐')
    assert '秒' not in result['positive_prompt'] and '60 BPM' in result['positive_prompt']
    assert '开场钢琴引入' in result['positive_prompt'] and '音乐持续至结束' in result['positive_prompt']
    assert '3秒' in normalize(value,'第3秒开始展开')['positive_prompt']


def test_empty_translated_negatives_cannot_be_silently_omitted():
    session=Mock();session.complete.return_value=(json.dumps(dict(caption='Epic orchestral instrumental',avoid='')), {})
    with pytest.raises(ValueError,match='避免内容不完整'):translate(session,'史诗配乐','不要人声')


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
    text.complete.return_value=(json.dumps(dict(caption='Edited solo violin.',avoid='Voices.')), {})
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
    if edited:
        assert 'without condensing' in text.complete.call_args.args[0][0]['content']
        assert text.complete.call_args.kwargs['max_tokens']==1400
    request=json.loads((tmp_path/'request.json').read_text('utf-8'))
    assert request['seconds']==29 and request['deliver_seconds']==20
    assert ('Edited solo violin' if edited else 'Original epic music') in request['caption']
    data=json.loads((tmp_path/'audio.json').read_text('utf-8'))
    assert data['status']=='completed' and data['duration_integrity']['target_seconds']==20
    assert data['duration_integrity']['trailing_removed_seconds']>3
