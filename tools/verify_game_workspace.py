"""Native UI and real lossless media checks for the unified game-asset workflow."""
import json
import tempfile
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import av
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog,QDockWidget
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from tools.verify_dock_workspace import wait_until,drop


def verify(area='layout'):
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,ExitStack() as cleanup,patch('aipictures.app.DATA',Path(temp)/'cache'), \
            patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        root=Path(temp);w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(60)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(50)
        b=w.workbench;vc=w.video_controller;w.intent_controller.config=None
        vc.h3={'validated':True};vc.motion_settings={'validated':True};vc.long_ready=vc.edit_ready=True
        assert [button.text() for button in b.modes]==['游戏CG','精灵图','音频']
        assert [b.right_tabs.tabText(i) for i in range(2)]==['参考','生成'] and b.right_tabs.currentIndex()==0
        assert not b.right_tabs.isMovable() and not b.workspace.childrenCollapsible()
        assert all(not dock.isVisible() for dock in w.findChildren(QDockWidget))
        assert b.task.parentWidget()==b.canvas and not w.output_shortcut.isEnabled()
        assert [a.text() for a in w.menuBar().actions()]==['记录','画面','采样','连接','API','窗口']
        if area in ('layout','sprite'):
            image=root/'person.png';Image.new('RGB',(64,96),'purple').save(image)
            frames=[Image.new('RGB',(64,96),(80+i*20,110,180)) for i in range(8)]
            gif=root/'motion.gif';frames[0].save(gif,save_all=True,append_images=frames[1:],duration=120,loop=0)
            original=(image.read_bytes(),gif.read_bytes())
            with patch('aipictures.professional_prompt.organize',side_effect=AssertionError('Import must not analyze')):
                drop(app,w.preview,[image]);drop(app,w.preview,[gif]);wait_until(lambda:not w.preparing)
            panel=vc.motion;assert panel.path and w.reference_path and not w.current and not w.pending
            assert abs(vc.seconds.value()-.96)<.002 and not panel.repeat.isChecked()
            assert b.reference_items.isAncestorOf(b.motion_item) and b.reference_items.isAncestorOf(b.reference_item)
            assert not b.timeline_region.isVisible() and not b.reference_skinning is False
            w.show_image(str(image));before=w.output,w.preview_path,w.preview_role,w.pixmap.cacheKey()
            b.right_tabs.setCurrentIndex(0);QTest.qWait(20)
            b.toggle_motion_reference();assert b.reference_player.timer.isActive();b.reference_player.toggle()
            assert (w.output,w.preview_path,w.preview_role,w.pixmap.cacheKey())==before
            b.right_tabs.setCurrentIndex(1);assert w.positive.isVisible() and not w.negative.isVisible()
            assert not w.intent_controller.input.isVisible() and not w.intent_controller.role.isVisible()
            request='将图1的人物替换到参考动画中，保持动作顺序'
            w.positive.setPlainText(request);w.negative.setPlainText('旧的错误反词')
            with patch.object(vc,'enqueue') as enqueue:
                assert vc.intercept();wait_until(lambda:not w.preparing)
            params=enqueue.call_args.args[0]
            assert params['prompt']==request and params['negative']=='' and params['motion_timeline']==[]
            assert params['motion_prompt_format']=='video_edit_multi_v1'
            assert Path(params['motion_reference']).read_bytes()==gif.read_bytes()
            assert Path(params['video_edit_refs'][0]['path']).is_file()
            assert original==(image.read_bytes(),gif.read_bytes())
            assert b.duration_note.isVisible() and '参考动画时长' in b.duration_note.text()
            folder=root/'frames';folder.mkdir()
            for i in (10,1,2):Image.new('RGB',(64,96),(i,40,70)).save(folder/f'frame_{i}.png')
            write_json(folder/'sprite_sheet.json',dict(fps=12))
            drop(app,b.motion_item,[folder]);wait_until(lambda:not w.preparing)
            mapping=json.loads((panel.path.parent/'source-map.json').read_text('utf-8'))
            assert [row['source'] for row in mapping]==['frame_1.png','frame_2.png','frame_10.png']
            assert abs(vc.seconds.value()-.25)<.002 and panel.meta['frame_count']==3
            assert w.reference_path and not b.timeline_region.isVisible()
            panel.clear();assert not b.motion_selection.isVisible()
            w.resize(1000,720);QTest.qWait(50);assert w.minimumHeight()<=720
            b.workspace.setSizes([550,400]);b.save_layout();b.right_tabs.setCurrentIndex(1);b.restore_layout();assert b.right_tabs.currentIndex()==0
        if area=='categories':
            b.select_category('long_video');QTest.qWait(20)
            assert vc.seconds.value()==6 and vc.seconds.maximum()==8 and w.short_video.isVisible()
            assert not b.timeline_region.isVisible() and w.generate_button.text()=='生成本段'
            w.audio_controller.config={'validated':True,'woosh':{'validated':True}}
            b.select_category('audio');QTest.qWait(20)
            assert w.tabs.currentWidget()==w.audio_controller.page and w.generate_button.isVisible()
            assert b.right_tabs.parentWidget()==w.audio_controller.page and b.task.parentWidget()==w.audio_controller.left
            a=w.audio_controller;a.prompt.setPlainText('史诗战斗配乐，不要音效');assert a.effective_kind()=='music' and a.seconds.minimum()==10
            a.prompt.setPlainText('金属剑碰撞的音效，不要背景音乐');assert a.effective_kind()=='sfx' and a.seconds.maximum()==5
            a.kind.setCurrentIndex(a.kind.findData('music'));assert a.effective_kind()=='music'
            b.select_category('sprite');assert b.right_tabs.parentWidget()==b.workspace and b.task.parentWidget()==b.canvas
        if area=='cg':
            from aipictures.video_generation import generate
            b.select_category('long_video');vc.seconds.setValue(2);w.short_video.brief.setPlainText('红色方块缓慢向右移动')
            def render(folder,params,*_):
                rgb=np.zeros((max(48,params.get('h3_frames',48)),16,16,3),dtype=np.uint8)
                rgb[...,0]=40 if not params.get('h3_continue_video') else 100
                np.save(folder/'fixture.npy',rgb);return dict(native_rgb=str(folder/'fixture.npy'))
            with patch.object(vc,'enqueue') as enqueue:assert vc.intercept()
            params,job=enqueue.call_args.args
            assert params['manual_segments'] and params['audio_mode']=='none' and not params['music_file']
            with patch('aipictures.h3_backend.generate',side_effect=render),patch('aipictures.video_audio.package',side_effect=AssertionError('Silent CG must not produce music')):
                first=generate(None,job,params,threading.Event(),lambda *_:None)
                player=vc.player;player.load(first['manifest']);player.stop()
                assert not player.has_audio and w.short_video.continuation_source==Path(first['manifest'])
                assert vc.seconds.maximum()==7 and not w.short_video.brief.toPlainText()
                w.short_video.brief.setPlainText('接下来方块变亮，继续移动')
                with patch.object(vc,'enqueue') as enqueue:assert vc.intercept()
                following,next_job=enqueue.call_args.args
                assert following['continue_from']==first['manifest'] and following['prompt']=='接下来方块变亮，继续移动'
                second=generate(None,next_job,following,threading.Event(),lambda *_:None)
            one=json.loads(Path(first['manifest']).read_text('utf-8'));two=json.loads(Path(second['manifest']).read_text('utf-8'))
            assert two['frame_count']==96 and two['duration_seconds']==4
            assert np.array_equal(np.load(one['native_rgb_source']),np.load(two['native_rgb_source'])[:48])
            with av.open(two['source_video']) as media:assert len(media.streams.video)==1 and not media.streams.audio and len(list(media.decode(video=0)))==96
            player.load(second['manifest']);player.toggle();player.slider.setValue(60);assert player.index==60
            exported=root/'result.mp4'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(exported),'')):player.save()
            wait_until(lambda:not w.preparing)
            assert exported.read_bytes()==Path(two['source_video']).read_bytes()
            w.short_video.start_new();assert not w.short_video.continuation_source and vc.seconds.maximum()==8
        print(f'Unified workspace {area}: PASS (native Qt, no model inference)')


if __name__=='__main__':
    import sys
    verify(sys.argv[1] if len(sys.argv)>1 else 'layout')
