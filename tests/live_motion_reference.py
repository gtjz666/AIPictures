import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from aipictures.app import Window,create_application
from tests.test_motion_reference import gif


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)),patch('aipictures.storage.DATA',Path(temp)),\
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'),\
         patch('aipictures.h3_backend.settings',return_value={'validated':True}),\
         patch('aipictures.motion_native_backend.settings',return_value={'validated':True}):
        root=Path(temp);w=Window();w.timer.stop();w.show();QTest.qWait(20)
        vc=w.video_controller;panel=vc.motion
        def wait():
            deadline=time.monotonic()+15
            while w.preparing or w.workers:
                app.processEvents();QTest.qWait(10)
                assert time.monotonic()<deadline
        assert not panel.isVisible() and not panel.path
        w.generation_type.setCurrentIndex(1);w.workbench.right_tabs.setCurrentIndex(1);assert panel.isVisible()
        source=gif(root/'walk.gif');before=source.read_bytes();panel.set_file(source);wait()
        assert panel.path and panel.meta['name']=='walk.gif' and w.animation_action.currentData()=='custom'
        assert 'walk.gif' in panel.summary.text()
        panel.preview();app.processEvents()
        assert panel.preview_dialog is None and w.workbench.reference_player.timer.isActive()
        assert w.preview_role=='motion_reference';w.workbench.reference_player.toggle()
        image=root/'character.png';Image.new('RGBA',(64,96),(20,100,220,255)).save(image)
        w.set_reference(str(image));w.positive.setPlainText('保持蓝色衣服，跟随动作参考');w.seed.setText('1234')
        with patch.object(w,'start_next'):
            QTest.mouseClick(w.generate_button,Qt.MouseButton.LeftButton)
            panel.clear();w.clear_reference();w.positive.setPlainText('下次任务');wait()
        assert len(w.pending)==1,w.chat.toPlainText()
        params=w.pending[0][1]
        assert params['prompt']=='保持蓝色衣服，跟随动作参考' and params['seed']==1234
        assert Path(params['motion_reference']).is_file() and Path(params['reference']).is_file()
        assert Path(params['motion_reference']).read_bytes()==before and source.read_bytes()==before
        w.clear_pending()
        pngs=[]
        for number,color in [(10,'blue'),(2,'green'),(1,'red')]:
            p=root/f'frame_{number}.png';Image.new('RGB',(64,96),color).save(p);pngs.append(str(p))
        with patch('aipictures.motion_reference_ui.QFileDialog.getOpenFileNames',return_value=(pngs,'PNG')),\
             patch('aipictures.motion_reference_ui.QInputDialog.getInt',return_value=(12,True)):
            QTest.mouseClick(panel.add_frames,Qt.MouseButton.LeftButton);wait()
        assert panel.path.suffix=='.json' and panel.meta['frame_count']==3 and panel.repeat.isChecked()
        w.positive.setPlainText('黄色小怪物按照动作帧移动')
        with patch.object(w,'start_next'):
            QTest.mouseClick(w.generate_button,Qt.MouseButton.LeftButton)
            panel.clear();wait()
        frozen=Path(w.pending[0][1]['motion_reference'])
        from aipictures.motion_guide import sequence
        data,frames=sequence(frozen)
        assert data['fps']==12 and len(frames)==3 and Image.open(frames[0]).getpixel((0,0))==(255,0,0)
        assert w.pending[0][1]['motion_repeat']
        w.clear_pending();w.generation_type.setCurrentIndex(0)
        assert panel.isVisible() and not panel.path and not w.reference_path
        w.close();app.processEvents()
    print('Motion/character separation, GIF + PNG buttons/FPS, preview, frozen queues, clear: PASS')


if __name__=='__main__':main()
