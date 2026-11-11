"""Native UI contract: sole request -> frozen inputs; never starts image/music/video inference."""
import argparse
import json
import tempfile
import threading
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog
from aipictures.app import Window,create_application
from aipictures.audio_prompt import fingerprint
from aipictures.storage import write_json
from tools.verify_dock_workspace import wait_until


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof',type=Path);args=parser.parse_args()
    if args.proof:args.proof.mkdir(parents=True,exist_ok=True)
    app=create_application([])
    with tempfile.TemporaryDirectory() as temporary,ExitStack() as cleanup,patch('aipictures.app.DATA',Path(temporary)/'data'), \
            patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
            patch('aipictures.motion_native_backend.release_shared'),patch('aipictures.intent_observation.observe',side_effect=AssertionError('No image analysis')):
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(40)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(40)
        root=Path(temporary);source=root/'character.png';Image.new('RGB',(16,24),'yellow').save(source);w.set_reference(str(source))
        w.intent_controller.config={'fixture':True};w.audio_controller.config={'validated':True};vc=w.video_controller
        vc.h3={'validated':True};vc.long_ready=True
        c=w.generation_intent;calls=[]
        # Retired hidden controls must never add invisible constraints or gates.
        w.intent_controller.role.setCurrentIndex(w.intent_controller.role.findData('custom'));w.intent_controller.role_note.clear()
        def organize(config,brief,negative,refs,motion,folder,cancel,emit,**kwargs):
            calls.append((brief,refs,kwargs));return dict(plan=dict(positive_prompt='整理：'+brief,negative_prompt=''),english=dict(positive='Prepared request: '+brief,negative=''))
        def music(config,brief,seconds,*args,**kwargs):
            positive='音乐整理：'+brief;return dict(positive_prompt=positive,negative_prompt='不要杂音',english_caption='Clear instrumental music, no artifacts.',caption_fingerprint=fingerprint(positive,'不要杂音'))
        with patch('aipictures.professional_prompt.organize',side_effect=organize),patch('aipictures.audio_prompt.organize',side_effect=music):
            for kind in ('image','animation','video','audio'):
                w.workbench.select_category('audio' if kind=='audio' else 'long_video' if kind=='video' else 'sprite')
                if kind in ('image','animation'):w.workbench.sprite_mode.setCurrentIndex(0 if kind=='image' else 1)
                w.workbench.right_tabs.setCurrentWidget(w.workbench.animation);QTest.qWait(20)
                brief={'image':'将图1的人物改成双手抱头，保留外形','animation':'先抱头惊叹，然后捧腹大笑，最后躺地打滚','video':'下一段镜头向右移动，不重复开场','audio':'舒缓又有淡淡悲伤的钢琴音乐'}[kind]
                editor=c.editor();editor.setPlainText(brief);w.negative.setPlainText('旧的紫发站姿与错误反词')
                with patch.object(w,'enqueue') as submit:
                    assert c.intercept();wait_until(lambda:not c.running);QTest.qWait(30)
                    assert submit.call_count==1 and editor.toPlainText()==brief
                prepared=c.current();assert prepared and prepared['source']['requirement']==brief
                assert prepared['source']['role']=='appearance' and not prepared['source']['usage']
                params={};c.record(params);assert params['user_prompt']==brief and params['source_brief']==brief and params['user_negative']==''
                assert '旧的紫发' not in c.prompts()[0]+c.prompts()[1]
                assert w.progress.maximum()==100 and not w.task_display.clock.isActive()
                assert w.generate_button.isVisible() and not w.negative.isVisible() and not w.intent_controller.input.isVisible()
                if kind in ('animation','video'):
                    with patch.object(vc,'enqueue') as enqueue:assert vc.intercept()
                    frozen=enqueue.call_args.args[0];assert brief in frozen['prompt'] and frozen['negative']==''
                    assert frozen['motion_timeline']==[]
                    if kind=='video':assert frozen['manual_segments'] and not frozen['continue_from']
                if kind=='audio':
                    with patch.object(w,'start_next'):w.audio_controller.enqueue()
                    frozen=w.pending[-1][1];assert frozen['source_brief']==brief and frozen['caption_english']=='Clear instrumental music, no artifacts.'
                    w.pending.clear()
                if args.proof:w.grab().save(str(args.proof/(kind+'.png')))
        # Editing during preprocessing must never send the previous requirement.
        started=threading.Event();release=threading.Event();previous=c.prepared
        w.workbench.select_category('sprite');w.workbench.sprite_mode.setCurrentIndex(0);w.positive.setPlainText('第一份请求')
        def delayed(*args,**kwargs):started.set();assert release.wait(10);return organize(*args,**kwargs)
        with patch('aipictures.professional_prompt.organize',side_effect=delayed),patch.object(w,'enqueue') as submit:
            assert c.intercept();wait_until(started.is_set);w.positive.setPlainText('用户中途改成第二份请求');release.set();wait_until(lambda:not c.running);QTest.qWait(20)
            assert submit.call_count==0 and c.prepared==previous and c.current() is None
        # Closing the export picker must stop protecting a completed boat cache.
        boat=w.api_controller.data/'videos'/'boat';boat.mkdir(parents=True);write_json(boat/'video.json',dict(status='completed',params=dict(prompt='船')))
        picker=QDialog(w);picker.manifest=boat/'video.json';picker.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);w.frame_selection_dialog=picker;picker.show();picker.close();QTest.qWait(30)
        vc.refresh_history();item=w.assets_dialog.videos.item(0);item.setSelected(True);w.clear_result_cache('video');wait_until(lambda:not w.cache_busy)
        assert not boat.exists()
        assert all(w.assets_dialog.tabs.tabText(i) not in ('已保存文件','素材文件夹') for i in range(w.assets_dialog.tabs.count()))
        assert not w.assets_dialog.cache_status.isVisible()
        if args.proof:write_json(args.proof/'acceptance.json',dict(single_requirement_all_modes=True,old_negative_not_submitted=True,
            original_text_preserved=True,no_visual_analysis=True,manual_one_segment=True,no_hidden_timeline=True,stale_result_not_submitted=True,
            busy_progress_finishes=True,closed_picker_cache_deletion=True,music_video_inference=False))
    print('Single request / all modes / frozen instructions / no visual analysis / progress / cache: PASS')


if __name__=='__main__':main()
