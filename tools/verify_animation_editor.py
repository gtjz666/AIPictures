"""Qt video-only drop, editable target actions, and queue snapshot. No model calls."""
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTableWidgetItem
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from aipictures.video_io import encode_pngs
from tools.verify_dock_workspace import drop,wait_until
import threading


def main():
    app=create_application([]);proof=Path('data/acceptance/animation-editor-qt-20261104').resolve();proof.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary,patch('aipictures.app.DATA',Path(temporary)/'cache'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        root=Path(temporary);paths=[]
        for i in range(8):
            p=root/f'{i}.png';Image.new('RGB',(96,144),(30+i*15,50,160)).save(p);paths.append(p)
        clip=root/'motion.mp4';encode_pngs(paths,clip,24,threading.Event())
        w=Window();w.timer.stop();w.resize(1280,800);w.show();QTest.qWait(100)
        b=w.workbench;vc=w.video_controller
        drop(app,w.preview,[clip]);wait_until(lambda:not w.preparing);QTest.qWait(100)
        assert w.reference_path is None and b.right_tabs.currentIndex()==1 and not w.pixmap.isNull()
        assert w.preview.pixmap() and not w.preview.pixmap().isNull() and b.reference_player.isVisible()
        assert vc.motion.buttons.count()==6 and vc.motion.buttons.itemAtPosition(0,2).widget()==b.analyze_motion
        assert not w.intent_controller.running and not w.current
        vc.seconds.setValue(32);assert vc.seconds.value()==32
        result=dict(plan=dict(kind='animation',timeline=[dict(start=0,end=.1,description='抬手'),dict(start=.1,end=.333,description='收手')]))
        w.positive.setPlainText('角色保持蓝色衣服');b.show_plan(result)
        assert b.timeline.isVisible() and b.timeline.table.rowCount()==2
        table=b.timeline.table;table.setItem(0,2,QTableWidgetItem('右手向镜头挥拳'))
        assert '右手向镜头挥拳' in w.positive.toPlainText() and b.timeline.rows()[0]['description']=='右手向镜头挥拳'
        vc.seconds.setValue(48);assert b.timeline.rows()[-1]['end']<=48
        table.setItem(0,0,QTableWidgetItem('NaN'))
        try:b.timeline.rows();raise AssertionError('Invalid timing accepted')
        except ValueError:pass
        table.setItem(0,0,QTableWidgetItem('0'))
        vc.h3={'validated':True};vc.motion_settings={'validated':True}
        # The actual controller must freeze edited rows into the queued job.
        with patch.object(vc,'enqueue') as enqueue:
            assert vc.intercept();wait_until(lambda:not w.preparing)
            assert enqueue.call_args.args[0]['motion_timeline'][0]['description']=='右手向镜头挥拳'
        w.positive.setPlainText('用户重新写的动作：向左走。')
        assert not b.timeline.effective_rows(),'Manual prompt replacement must not retain a hidden old timeline.'
        # A splitter resize must refresh the actual left preview, not just the Window.
        b.workspace.setSizes([650,550]);QTest.qWait(50)
        assert w.preview.pixmap().width()<=w.preview.width()*w.preview.devicePixelRatioF()+2
        w.grab().save(str(proof/'editor.png'))
        vc.motion.clear();assert not b.timeline.isVisible() and not b.timeline.rows()
        w.close();QTest.qWait(40)
    write_json(proof/'acceptance.json',dict(passed=True,actual_qt=True,no_inference=True,video_only=True,editable_queue=True))
    print('Animation editor / six buttons / video-only canvas / duration / editable queued timeline: PASS')


if __name__=='__main__':main()
