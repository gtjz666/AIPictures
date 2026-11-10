"""Native Qt music prompt editing, stale-result protection and frozen captions. No music inference."""
import argparse
import copy
import json
import tempfile
import threading
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPlainTextEdit,QPushButton
from aipictures.app import Window,create_application
from aipictures.audio_prompt import fingerprint
from aipictures.engine import Cancelled
from tools.verify_dock_workspace import wait_until


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path);parser.add_argument('--audio',type=Path);parser.add_argument('--proof',type=Path)
    args=parser.parse_args();app=create_application([])
    if args.proof:args.proof.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary,ExitStack() as cleanup,patch('aipictures.app.DATA',Path(temporary)/'cache'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
         patch('aipictures.motion_native_backend.release_shared'),patch('aipictures.audio_generation.subprocess.Popen',side_effect=AssertionError('Organizing must never start music generation')):
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(60)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(40)
        a=w.audio_controller;p=a.prompt_tools;a.config={'validated':True};w.intent_controller.config={'fixture':True}
        w.workbench.select_category('audio');a.seconds.setValue(20);a.prompt.setPlainText('压迫感史诗配乐，层层推进，乐器清晰。')
        image_words=w.positive.toPlainText()
        def organize(config,brief,seconds,*other,**kwargs):
            positive=kwargs.get('manual_prompt') or '史诗管弦配乐，低音弦乐开场，铜管与大鼓递进，高潮后自然收束。'
            negative=kwargs.get('exclusions') or '人声、底噪、爆音'
            return dict(positive_prompt=positive,negative_prompt=negative,english_caption='Epic instrumental with clear strings and brass; no voices or noise.',
                caption_fingerprint=fingerprint(positive,negative),source_brief=brief,seconds=seconds)
        with patch('aipictures.audio_prompt.organize',side_effect=organize) as model:
            p.organize.click();wait_until(lambda:not w.preparing)
            assert model.call_count==1 and not w.pending and p.draft and w.positive.toPlainText()==image_words
            a.seconds.setValue(21)
            try:a.enqueue();raise AssertionError('Changed duration reused the old prompt')
            except ValueError:pass
            assert not w.pending
            a.seconds.setValue(20)
            with patch.object(w,'start_next'):a.enqueue()
            params=w.pending[0][1];assert params['caption_english']==p.draft['english_caption'] and params['negative']
            w.pending.clear()
            p.edit.click();QTest.qWait(40);d=p.dialog
            d.findChild(QPlainTextEdit,'audioPositive').setPlainText('手动改为圆号主奏，保留弦乐递进。')
            d.findChild(QPlainTextEdit,'audioAvoid').setPlainText('不要电吉他。')
            next(button for button in d.findChildren(QPushButton) if button.text()=='应用修改').click();QTest.qWait(20)
            assert p.snapshot()['caption_english'] is None and '圆号' in p.snapshot()['prompt']
            frozen=dict(p.snapshot(),seconds=a.seconds.value())
            p.remember_caption(frozen,'Edited horn-led instrumental, no electric guitar.')
            assert p.snapshot()['caption_english'].startswith('Edited horn')
            p.remember_caption(dict(frozen,prompt='different old queued text'),'Must not replace the current caption')
            assert p.snapshot()['caption_english'].startswith('Edited horn')
            p.organize.click();wait_until(lambda:not w.preparing)
            assert model.call_args.kwargs['manual_prompt'].startswith('手动改为') and model.call_args.kwargs['exclusions']=='不要电吉他。'
            a.prompt.setPlainText('新的钢琴独奏要求')
            p.organize.click();wait_until(lambda:not w.preparing)
            assert model.call_args.kwargs['manual_prompt']==model.call_args.kwargs['exclusions']==''
        previous=copy.deepcopy(p.draft);started=threading.Event();release=threading.Event()
        def delayed(*args,**kwargs):started.set();release.wait(10);return organize(*args,**kwargs)
        with patch('aipictures.audio_prompt.organize',side_effect=delayed):
            p.organize.click();wait_until(started.is_set);a.prompt.setPlainText('任务中途修改要求');release.set();wait_until(lambda:not w.preparing)
        assert p.draft==previous and not w.pending
        def cancelled(*args,**kwargs):
            started.set();w.intent_controller.cancel_event.wait(10);raise Cancelled('cancelled')
        started.clear()
        with patch('aipictures.audio_prompt.organize',side_effect=cancelled):
            p.organize.click();wait_until(started.is_set);w.cancel_current();wait_until(lambda:not w.preparing)
        assert p.draft==previous and not w.pending
        if args.plan:
            value=json.loads(args.plan.read_text('utf-8'));a.prompt.setPlainText(value['source_brief']);a.seconds.setValue(value['seconds']);p.draft=value
            if args.audio:a.load(args.audio)
            if args.proof:w.grab().save(str(args.proof/'audio-requirements.png'))
            p.edit.click();QTest.qWait(50)
            if args.proof:p.dialog.grab().save(str(args.proof/'editable-music-prompts.png'))
            p.dialog.close()
        if args.proof:(args.proof/'acceptance.json').write_text(json.dumps(dict(explicit_only=True,no_music_started=True,manual_edits=True,cached_english=True,stale_and_cancelled_results_discarded=True,
            real_plan=str(args.plan.resolve()) if args.plan else None,independent_duration_comparison=str(args.audio.resolve()) if args.audio else None)),'utf-8')
    print('Audio prompt UI / manual edits / English cache / stale and cancellation guards: PASS')


if __name__=='__main__':main()
