"""Real Qt category navigation, 30s queue and independent audio queue; no models."""
import tempfile
import argparse
import json
import shutil
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.video_script import simple
from tools.verify_dock_workspace import wait_until


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--video',type=Path);parser.add_argument('--audio',type=Path)
    parser.add_argument('--proof',type=Path);args=parser.parse_args();app=create_application([])
    if args.proof:args.proof.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary,ExitStack() as cleanup,patch('aipictures.app.DATA',Path(temporary)/'cache'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(80)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(50)
        b=w.workbench;vc=w.video_controller
        assert [button.text() for button in b.modes]==['长视频','精灵图','音频']
        assert b.category=='sprite' and [b.sprite_mode.itemText(i) for i in range(2)]==['单张','动画帧']
        vc.h3={'validated':True};vc.long_ready=True
        b.select_category('long_video');QTest.qWait(30)
        assert vc.seconds.value()==30 and vc.seconds.maximum()==45 and w.short_video.isVisible()
        assert not b.sprite_action.isVisible() and not b.sprite_mode.isVisible()
        assert not b.timeline_region.isVisible() and w.generate_button.text()=='生成长视频'
        w.positive.setPlainText('之前精灵图的静态角色要求')
        w.short_video.brief.setPlainText('湖面的船缓慢前进')
        assert w.short_video.snapshot()['overview']=='湖面的船缓慢前进'
        w.short_video.apply(simple('湖面的船缓慢前进',30))
        before=w.positive.toPlainText();w.short_video.music.setCurrentIndex(w.short_video.music.findData('bright'));w.short_video.reset_music()
        assert w.positive.toPlainText()!=before and w.short_video.snapshot()['music_style']=='bright'
        w.positive.setPlainText('手动修改的视频要求');w.short_video.music.setCurrentIndex(0);w.short_video.reset_music()
        assert w.positive.toPlainText()=='手动修改的视频要求'
        w.short_video.apply(simple('湖面的船缓慢前进',30))
        with patch.object(vc,'enqueue') as queue:
            assert vc.intercept();params,folder=queue.call_args.args
        assert params['creation_kind']=='long_video' and params['seconds']==30 and params['audio_mode']=='h3_native'
        b.select_category('sprite');b.sprite_mode.setCurrentIndex(1);QTest.qWait(20)
        assert w.generation_type.currentData()=='walk' and b.timeline_region.isVisible() and not w.short_video.isVisible()
        b.sprite_mode.setCurrentIndex(0);assert w.generation_type.currentData()=='image'
        w.audio_controller.config={'validated':True};b.select_category('audio');QTest.qWait(20)
        assert w.tabs.currentWidget()==w.audio_controller.page and w.generate_button.text()=='生成音频'
        assert not b.sprite_action.isVisible()
        assert w.task_display.isVisible() and not w.preview.isVisible()
        w.audio_controller.prompt.setPlainText('舒缓的钢琴背景配乐，无人声')
        with patch.object(w,'start_next'):w.enqueue()
        assert len(w.pending)==1 and w.pending[0][1]['mode']=='audio'
        w.pending.clear()
        if args.video and args.audio:
            from PySide6.QtWidgets import QFileDialog,QListWidgetItem
            from PySide6.QtCore import Qt
            item=QListWidgetItem();item.setData(Qt.ItemDataRole.UserRole,str(args.video));vc.open_history(item)
            assert b.category=='long_video' and w.tabs.currentWidget()==b.workspace
            wait_until(lambda:vc.player.sound.position()>120,seconds=12);vc.player.toggle();vc.player.slider.setValue(360)
            assert vc.player.count==720 and vc.player.index==360
            if args.proof:w.grab().save(str(args.proof/'long-video-workspace.png'))
            video_target=Path(temporary)/'full-video.mp4'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(video_target),'')):vc.player.save()
            assert video_target.read_bytes()==vc.player.source.read_bytes()
            b.select_category('audio');audio=w.audio_controller;audio.load(args.audio);audio.toggle()
            wait_until(lambda:audio.player.position()>120,seconds=12);audio.toggle();audio.slider.setValue(15000);audio.player.setPosition(15000)
            if args.proof:w.grab().save(str(args.proof/'audio-workspace.png'))
            target=Path(temporary)/'exported.wav'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):audio.save()
            assert target.read_bytes()==audio.audio.read_bytes()
            # Navigation pauses audio. Explicit release must also be recoverable.
            b.select_category('sprite');assert audio.player.playbackState()!=audio.player.PlaybackState.PlayingState
            audio.stop();assert audio.player.source().isEmpty()
            if args.proof:w.grab().save(str(args.proof/'sprite-workspace.png'))
            b.select_category('audio');audio.toggle();wait_until(lambda:audio.player.position()>100,seconds=12);audio.toggle()
            b.select_category('long_video');vc.player.toggle();wait_until(lambda:vc.player.sound.position()>120,seconds=12);vc.player.toggle()
            if args.proof:(args.proof/'acceptance.json').write_text(json.dumps(dict(real_video=str(args.video.resolve()),real_audio=str(args.audio.resolve()),video_frames=720,audio_export_exact=True,navigation_playback_restored=True),ensure_ascii=False,indent=2),'utf-8')
        w.close();QTest.qWait(50)
    print('Three categories / sprite subtypes / 30s video / independent audio: PASS')


if __name__=='__main__':main()
