"""Native Qt short-film composer, script guards, sound playback and export. CPU fixtures."""
import json
import tempfile
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import av
import argparse
from PySide6.QtTest import QTest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog,QApplication,QTableWidget,QTableWidgetItem,QPushButton
from aipictures.app import Window,create_application
from aipictures import video_script
from aipictures.video_audio import compose_music,save_wav
from aipictures.video_generation import generate
from aipictures.storage import write_json
from tests.test_short_video import picture_source,decode
from tools.verify_dock_workspace import wait_until


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path);parser.add_argument('--proof',type=Path,default=Path('data/acceptance/short-video-ui-20261110'))
    args=parser.parse_args();app=create_application([]);proof=args.proof;proof.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp,ExitStack() as cleanup,patch('aipictures.app.DATA',Path(temp)/'cache'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
         patch('aipictures.intent_controller.settings',return_value={'name':'protocol fixture'}):
        root=Path(temp);w=Window();w.timer.stop();w.resize(1400,940);w.show();QTest.qWait(50)
        def close_window():w.close();QTest.qWait(80)
        cleanup.callback(close_window)
        b=w.workbench;vc=w.video_controller;panel=w.short_video;vc.h3={'validated':True};vc.apply_ui()
        w.generation_type.setCurrentIndex(w.generation_type.findData('walk'))
        b.right_tabs.setCurrentWidget(b.animation);b.creation_kind.setCurrentIndex(b.creation_kind.findData('short_video'))
        QTest.qWait(30)
        assert panel.isVisible() and not b.timeline_region.isVisible()
        assert not b.creation_kind.model().item(b.creation_kind.findData('long_video')).isEnabled()
        assert w.generate_button.text()=='生成短视频' and w.reference_path is None
        vc.seconds.setValue(2);panel.brief.setPlainText('清晨湖面，红色木船缓慢前行，水声和舒缓旋律。')
        w.negative.setPlainText('不要字幕')
        def organize(*args,**kwargs):return video_script.simple(args[1],args[2],args[3],'主体结构异常')
        with patch('aipictures.video_script.organize',side_effect=organize),patch('aipictures.motion_native_backend.release_shared'):
            panel.prepare();wait_until(lambda:not w.preparing)
            panel.prepare();wait_until(lambda:not w.preparing)
        assert panel.script and '0.000–2.000秒' in w.positive.toPlainText() and w.negative.toPlainText()
        assert w.negative.toPlainText().count('不要字幕')==1 and w.negative.toPlainText().count('主体结构异常')==1
        assert not w.intent_controller.running and w.generate_button.isEnabled()
        original_brief=panel.brief.toPlainText();panel.brief.setPlainText('改为夜晚，远景')
        try:panel.snapshot();raise AssertionError('Changed requirements silently used the old script')
        except ValueError:pass
        panel.brief.setPlainText(original_brief)
        imported=root/'music.wav';save_wav(imported,compose_music(.3,'bright',7));panel.music_file=str(imported)
        with patch.object(vc,'enqueue') as queue:
            assert vc.intercept();params,folder=queue.call_args.args
        assert params['creation_kind']=='short_video' and params['motion_timeline']==[]
        assert Path(params['music_file']).parent==folder and Path(params['music_file']).read_bytes()==imported.read_bytes()
        assert params['prompt']==w.positive.toPlainText() and (folder/'script.json').exists()
        vc.seconds.setValue(4)
        with patch.object(vc,'new_folder') as new:
            try:vc.intercept();raise AssertionError('Mismatched storyboard entered queue')
            except ValueError:pass
            new.assert_not_called()
        original_script=panel.script;negative=w.negative.toPlainText()
        def repair_script():
            dialog=QApplication.activeModalWidget();table=dialog.findChild(QTableWidget)
            table.setItem(0,1,QTableWidgetItem('4'))
            next(button for button in dialog.findChildren(QPushButton) if button.text()=='应用脚本与提示词').click()
        QTimer.singleShot(50,repair_script);panel.open_script()
        assert panel.script['duration_seconds']==4 and panel.script['shots'][0]['end']==4
        assert w.negative.toPlainText()==negative
        vc.seconds.setValue(2);panel.apply(original_script)
        b.open_prompts();QTest.qWait(40);b.prompts_dialog.grab().save(str(proof/'prompts.png'));b.prompts_dialog.close()
        w.grab().save(str(proof/'short-composer.png'))
        # Real media encoders and Qt audio decoder, while backend is a declared fixture.
        if args.manifest:result=dict(manifest=str(args.manifest.resolve()))
        else:
            job=root/'fixture';job.mkdir();rgb,_,array=picture_source(job,48)
            fixture=dict(params,reference=None,music_file=None)
            with patch('aipictures.h3_backend.generate',return_value=dict(native_rgb=str(rgb))):
                result=generate(None,job,fixture,threading.Event(),lambda *_:None)
        player=vc.player;positions=[];player.sound.positionChanged.connect(positions.append)
        player.load(result['manifest'])
        assert player.has_audio and not player.sound.source().isEmpty()
        wait_until(lambda:any(position>120 for position in positions),seconds=5)
        assert player.sound.error()==player.sound.Error.NoError,player.sound.errorString()
        player.toggle();assert not player.timer.isActive()
        player.slider.setValue(24);QTest.qWait(20);assert abs(player.sound.position()-1000)<130
        exports=root/'exports';exports.mkdir();complete=exports/'complete.mp4'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(complete),'')):player.save()
        assert complete.read_bytes()==Path(player.source).read_bytes()
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(exports)):
            player.export_tracks('both');wait_until(lambda:not w.preparing)
        separated=next(exports.glob('AlI_*'))
        assert (separated/'soundtrack.wav').exists()
        with av.open(str(separated/'video.mp4')) as c:assert not c.streams.audio
        assert len(decode(separated/'video.mp4'))==48
        w.grab().save(str(proof/'av-preview.png'))
        b.creation_kind.setCurrentIndex(b.creation_kind.findData('sprite'));QTest.qWait(10)
        assert b.timeline_region.isVisible() and not panel.isVisible()
        w.close();QTest.qWait(30);assert not player.timer.isActive()
        write_json(proof/'acceptance.json',dict(native_qt=True,model_calls='fixtures',real_media_roundtrip=True,
            media_source=str(args.manifest.resolve()) if args.manifest else 'CPU fixture',
            audio_clock_advanced=True,seek_synced=True,full_export_retained_audio=True,separate_export=True,
            frozen_music=True,invalid_duration_blocked=True,invalid_script_repairable=True,changed_brief_blocked=True,manual_exclusions_retained=True,long_disabled=True))
    print('Short-film Qt composer / audio playback / script clock / separation: PASS')


if __name__=='__main__':main()
