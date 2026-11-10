"""Native UI multi-picture/source-video import, exact requirements and frozen queue. No model."""
import tempfile
import argparse
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from tools.verify_dock_workspace import wait_until


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--video',type=Path);parser.add_argument('--proof',type=Path)
    args=parser.parse_args();app=create_application([])
    if args.proof:args.proof.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary,ExitStack() as cleanup,patch('aipictures.app.DATA',Path(temporary)/'cache'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        root=Path(temporary);a=root/'person.png';b=root/'style.png'
        Image.new('RGB',(32,48),'purple').save(a);Image.new('RGB',(32,48),'cyan').save(b)
        source=root/'motion.gif';Image.new('RGB',(32,48),'red').save(source,save_all=True,append_images=[Image.new('RGB',(32,48),'blue')],duration=250,loop=0)
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(60)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(30);vc=w.video_controller
        vc.h3={'validated':True};vc.motion_settings={'validated':True};vc.long_ready=vc.edit_ready=True
        w.workbench.select_category('long_video');w.intent_controller.import_files([a,b,source]);wait_until(lambda:not w.preparing)
        assert len(w.reference_chat.references())==2 and vc.motion.path and w.pixmap.isNull()
        assert not w.workbench.image_requirements.isVisible()
        assert not w.generate_button.isEnabled()
        with patch.object(vc,'new_folder') as create:
            try:vc.intercept();raise AssertionError('Unvalidated long source-video editing reached generation')
            except ValueError:pass
            create.assert_not_called()
        vc.seconds.setValue(2)
        w.short_video.brief.setPlainText('人物替换为图1，图2只取Q版画风，动作跟随原视频。')
        w.intent_controller.config=None;w.short_video.prepare();wait_until(lambda:not w.preparing)
        assert 'Q版' in w.positive.toPlainText() and 'Q版' not in w.negative.toPlainText()
        assert not vc.motion.repeat.isChecked()
        with patch.object(vc,'new_folder') as create:
            try:vc.intercept();raise AssertionError('Short source silently held for 30 seconds')
            except ValueError:pass
            create.assert_not_called()
        vc.motion.repeat.setChecked(True)
        with patch.object(vc,'enqueue') as queue:
            assert vc.intercept();wait_until(lambda:not w.preparing)
        params,folder=queue.call_args.args
        assert params['creation_kind']=='long_video_edit' and len(params['video_edit_refs'])==2
        assert params['motion_repeat'] and not params['motion_allow_tail_hold']
        assert params['video_edit_refs'][1]['model_input']==2
        assert all(Path(ref['path']).is_file() and ref['sha256'] for ref in params['video_edit_refs'])
        vc.h3={};vc.apply_ui();assert not w.generate_button.isEnabled()
        with patch.object(vc,'new_folder') as create:
            try:vc.intercept();raise AssertionError('Missing native audio components started expensive generation')
            except ValueError:pass
            create.assert_not_called()
        vc.h3={'validated':True};vc.apply_ui()
        w.positive.setPlainText('改成图4的人物')
        with patch.object(vc,'new_folder') as create:
            try:vc.intercept();raise AssertionError('Missing numbered picture reached the backend')
            except ValueError:pass
            create.assert_not_called()
        if args.video:
            data=json.loads(args.video.read_text('utf-8'));params=data['params']
            w.clear_reference();w.reference_chat.extra.clear()
            w.intent_controller.import_files([Path(ref['path']) for ref in params['video_edit_refs']]+[Path(params['motion_reference'])])
            wait_until(lambda:not w.preparing);vc.motion.repeat.setChecked(True)
            w.short_video.music.setCurrentIndex(w.short_video.music.findData(params['music_style']))
            vc.seconds.setValue(params['seconds'])
            w.short_video.brief.setPlainText(data['short_script']['overview']);w.short_video.apply(data['short_script'])
            vc.player.load(args.video);vc.player.toggle();vc.player.slider.setValue(300)
            before=w.pixmap.cacheKey();w.workbench.show_motion_reference(play=True);QTest.qWait(150);w.workbench.reference_player.stop()
            assert w.pixmap.cacheKey()==before and len(w.reference_chat.references())==2
            if args.proof:
                w.grab().save(str(args.proof/'source-video-editing.png'))
                w.workbench.right_tabs.setCurrentWidget(w.workbench.reference_items);QTest.qWait(40)
                w.grab().save(str(args.proof/'numbered-person-style-references.png'))
                (args.proof/'acceptance.json').write_text(json.dumps(dict(video=str(args.video.resolve()),references=2,reference_preview_preserves_result=True),ensure_ascii=False,indent=2),'utf-8')
        w.close();QTest.qWait(40)
    print('Source-video editing / numbered pictures / style request / source length guards: PASS')


if __name__=='__main__':main()
