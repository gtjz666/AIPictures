"""Actual Qt manual prompt workflow across images, animation, CG and audio."""
import argparse,json,tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from aipictures.app import Window,create_application
from aipictures.storage import write_json


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof',type=Path);args=parser.parse_args()
    if args.proof:args.proof.mkdir(parents=True,exist_ok=True)
    app=create_application([])
    with tempfile.TemporaryDirectory() as temporary,ExitStack() as cleanup:
        data=Path(temporary)/'data'
        for target in ('aipictures.app.DATA','aipictures.storage.DATA'):cleanup.enter_context(patch(target,data))
        for method in ('auto_connect_engine','restore_chat','refresh_stats'):cleanup.enter_context(patch.object(Window,method))
        for target in ('aipictures.local_intent.LocalSession.__enter__','aipictures.audio_prompt.TextSession.__enter__','aipictures.prompt_language.translate'):
            cleanup.enter_context(patch(target,side_effect=AssertionError('Manual generation must never call an assistant')))
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(40)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(60)
        source=Path(temporary)/'reference.png';Image.new('RGB',(64,96),'yellow').save(source);w.set_reference(source)
        assert w.intent_controller.config is None and not hasattr(w.workbench,'prepare_prompt')
        assert not hasattr(w.audio_controller,'prompt_tools')
        vc=w.video_controller;vc.h3={'validated':True};vc.long_ready=True
        audio=w.audio_controller;audio.config={'validated':True,'woosh':{'validated':True}}
        intent=w.generation_intent;proofs=[]
        for category,mode,brief in [('sprite','image','居中木箱，蓝色水彩。'),('sprite','walk','角色向前行走，然后停下。'),('long_video',None,'古堡大门开启，镜头向前推进。'),('audio','music','低沉弦乐开场，铜管层层推进，无人声。'),('audio','sfx','两次清脆的金属撞击，短促回响。')]:
            w.workbench.select_category(category)
            if category=='sprite':w.workbench.sprite_mode.setCurrentIndex(w.workbench.sprite_mode.findData(mode))
            if category=='audio':audio.kind.setCurrentIndex(audio.kind.findData(mode))
            w.workbench.right_tabs.setCurrentIndex(1);intent.editor().setPlainText(brief);QTest.qWait(30)
            assert intent.editor().isVisible() and w.generate_button.isVisible()
            assert not any(b.isVisible() for b in w.findChildren(QPushButton) if b.objectName()=='promptGenerate')
            assert intent.prompts()==(brief,'') and not intent.intercept()
            contract=intent.current();assert contract['manual'] and not contract['professionalized'] and contract['english'] is None
            w.negative.setPlainText('OLD HIDDEN WORDS MUST NOT LEAK')
            params={};intent.record(params);assert params['user_prompt']==brief and params['user_negative']==''
            if category=='audio':
                with patch.object(w,'start_next'):audio.enqueue()
                params=w.pending[-1][1];assert params['prompt']==brief and not params['negative']
                assert 'intent_settings' not in params and 'caption_english' not in params
                w.clear_pending()
            elif mode=='walk' or category=='long_video':
                with patch.object(vc,'enqueue') as queue:assert vc.intercept()
                params=queue.call_args.args[0];assert params['prompt']==brief and params['negative']=='' and not params['motion_timeline']
                if category=='long_video':assert params['manual_segments'] and not params['continue_from']
            frozen=json.loads(json.dumps(params));intent.editor().setPlainText(brief+'改为新的要求。')
            assert intent.current()['positive']==brief+'改为新的要求。' and params==frozen
            intent.editor().setPlainText(brief)
            assert not w.preparing and not w.current and not w.pending and not w.task_display.clock.isActive()
            if args.proof:w.grab().save(str(args.proof/(category+'-'+str(mode)+'.png')))
            proofs.append(dict(category=category,mode=mode,prompt=brief,manual_only=True))
        w.workbench.select_category('sprite');w.workbench.sprite_mode.setCurrentIndex(0)
        assert w.positive.toPlainText()=='居中木箱，蓝色水彩。'
        w.positive.setPlainText('采用图4的画风')
        import pytest
        with pytest.raises(ValueError,match='图4'):intent.intercept()
        w.positive.clear()
        with pytest.raises(ValueError,match='填写提示词'):intent.intercept()
        w.intent_controller.start(False);w.short_video.prepare();assert not w.preparing
        assert not (data/'intent').exists()
        if args.proof:write_json(args.proof/'acceptance.json',dict(cases=proofs,assistant_used=False,model_inference=False,missing_reference_rejected=True,frozen_jobs=True,mode_drafts=True))
    print('Manual Qt prompts in every category / no assistant or translation / frozen jobs / mode drafts: PASS')


if __name__=='__main__':main()
