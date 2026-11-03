"""Real Qt file drops, explicit analysis, fixed tabs and size persistence. No GPU."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData,QUrl
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QDockWidget

from aipictures.app import Window,create_application
from aipictures.storage import write_json


def wait_until(predicate,seconds=20):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        QTest.qWait(20);time.sleep(.005)  # Let Python worker threads run between Qt waits.
    assert predicate(),'Qt operation did not finish.'


def drop(app,widget,paths):
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    enter=QDragEnterEvent(QPoint(10,10),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    app.sendEvent(widget,enter);assert enter.isAccepted()
    event=QDropEvent(QPointF(10,10),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    app.sendEvent(widget,event);assert event.isAccepted()


def main():
    app=create_application([]);proof=Path('data/acceptance/dock-workspace').resolve();proof.mkdir(parents=True,exist_ok=True)
    calls=[]
    def recognize(config,brief,negative,reference,motion,folder,cancel,emit,**kwargs):
        calls.append(kwargs)
        plan=dict(kind=kwargs['selected_kind'],summary='仅用于界面协议检查',positive_prompt='参考角色抬手挥向镜头，再收回手臂。',
            negative_prompt=negative,observations=[],timeline=[dict(start=0,end=.5,description='抬手并收回')],questions=[])
        result=dict(plan=plan,model='protocol fixture',route='h3_reference',elapsed_seconds=.1)
        write_json(folder/'plan.json',result);return result
    with tempfile.TemporaryDirectory() as temporary,patch('aipictures.app.DATA',Path(temporary)/'cache'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
         patch('aipictures.intent_controller.settings',return_value={'name':'protocol fixture'}), \
         patch('aipictures.intent_controller.analyze',side_effect=recognize):
        root=Path(temporary);image=root/'character.png';Image.new('RGBA',(900,1600),(110,80,180,255)).save(image)
        write_json(root/'cache/workspace-layout.json',dict(schema_version=1,state='old-floating-layout'))
        frames=[Image.new('RGB',(96,144),(60+i*25,90,180)) for i in range(8)]
        gif=root/'motion.gif';frames[0].save(gif,save_all=True,append_images=frames[1:],duration=[120]*8,loop=0)
        w=Window();w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(80);b=w.workbench;c=w.intent_controller
        assert w.windowTitle()=='AlI' and not c.input.acceptDrops()
        assert b.canvas.x()<b.right_tabs.x() and b.right_tabs.count()==2
        assert [b.right_tabs.tabText(i) for i in range(2)]==['提示词','动画']
        assert not b.right_tabs.isMovable() and not b.workspace.childrenCollapsible()
        assert all(not dock.isVisible() for dock in w.findChildren(QDockWidget))
        assert b.task.parentWidget()==b.canvas
        assert not w.inspector.isVisible() and not w.output_shortcut.isEnabled()
        assert [a.text() for a in w.menuBar().actions()]==['记录','生成','画面','采样','连接','API','窗口']
        assert all(not label.isVisible() for label in (w.creation_summary,w.reference_label,w.context_label,w.intent_hint,w.seed_notice))
        before=image.read_bytes(),gif.read_bytes();drop(app,w.preview,[image]);QTest.qWait(350)
        assert w.reference_path and Path(w.reference_path)!=image and w.preview_role=='reference'
        assert b.reference_thumb.isVisible() and len(calls)==0 and not w.current and not w.pending
        assert b.reference_thumb.mapTo(w,QPoint(0,0)).x()<b.right_tabs.mapTo(w,QPoint(0,0)).x()
        reference=w.reference_path;drop(app,w.preview,[gif]);wait_until(lambda:not w.preparing)
        QTest.qWait(300);panel=w.video_controller.motion
        assert w.reference_path==reference and panel.path and w.preview_role=='motion_reference' and len(calls)==0
        assert b.reference_player.isVisible() and b.reference_player.paths
        assert b.right_tabs.currentIndex()==1 and panel.isVisible() and not b.prompts.isVisible()
        b.right_tabs.setCurrentIndex(0);QTest.qWait(20)
        assert b.prompts.isVisible() and not panel.isVisible()
        b.right_tabs.setCurrentIndex(1)
        QTest.mouseClick(b.reference_player.play,Qt.MouseButton.LeftButton);assert b.reference_player.timer.isActive()
        QTest.mouseClick(b.reference_player.play,Qt.MouseButton.LeftButton);assert not b.reference_player.timer.isActive()
        QTest.mouseClick(panel.range_button,Qt.MouseButton.LeftButton);assert panel.range_dialog.isVisible()
        panel.range_slider.setValue(500);assert panel.start.value()>0;panel.range_dialog.close()
        w.positive.setPlainText('角色模仿参考动作')
        QTest.mouseClick(b.analyze_motion,Qt.MouseButton.LeftButton);wait_until(lambda:not c.running)
        assert len(calls)==1 and '抬手' in w.positive.toPlainText() and not c.note.isVisible()
        assert not c.intercept(),'Generation must not trigger another analysis.'
        assert not w.current and not w.pending and before==(image.read_bytes(),gif.read_bytes())
        # PNG sequence import keeps the still character reference separate.
        pngs=[]
        for i in (10,2):
            path=root/f'frame_{i}.png';Image.new('RGBA',(96,144),(i,20,180,255)).save(path);pngs.append(path)
        with patch('aipictures.intent_controller.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes), \
             patch('aipictures.intent_controller.QInputDialog.getInt',return_value=(24,True)):
            drop(app,w.preview,pngs);wait_until(lambda:not w.preparing)
        QTest.qWait(300);assert panel.path.suffix=='.json' and w.reference_path==reference and len(calls)==1
        assert b.plan is None and not b.timeline.isVisible(), 'A changed motion source must not retain an old analysis.'
        w.resize(1280,800);QTest.qWait(40)
        assert w.size().height()<=820,'References must also fit the compact layout.'
        w.resize(1440,940);QTest.qWait(30)
        w.status.setText('已导出 1 帧：C:\\temporary\\sprite.png');w.progress.setValue(100)
        assert 'temporary' not in w.status.text() and not w.task_display.detail.isVisible() and b.task.height()<110
        w.grab().save(str(proof/'workspace.png'))
        assert b.task.mapTo(w,QPoint(0,0)).x()+b.task.width()<=b.canvas.mapTo(w,QPoint(0,0)).x()+b.canvas.width()+2
        b.workspace.setSizes([760,540]);b.prompt_splitter.setSizes([240,160]);b.right_tabs.setCurrentIndex(1)
        b.save_layout();saved=json.loads((root/'cache/workspace-layout.json').read_text('utf-8'))
        assert saved['schema_version']==2
        ratio=saved['columns'][0]/sum(saved['columns'])
        w.close();QTest.qWait(40)
        restored=Window();restored.timer.stop();restored.show();QTest.qWait(70)
        sizes=restored.workbench.workspace.sizes()
        assert abs(sizes[0]/sum(sizes)-ratio)<.05 and restored.workbench.right_tabs.currentIndex()==1
        restored.workbench.reset_layout();QTest.qWait(60)
        assert restored.workbench.canvas.x()<restored.workbench.right_tabs.x() and restored.workbench.right_tabs.currentIndex()==0
        restored.resize(1280,800);QTest.qWait(40);assert restored.size().height()<=820
        restored.grab().save(str(proof/'compact.png'))
        restored.workbench.right_tabs.setCurrentIndex(1);restored.positive.clear()
        QTest.mouseClick(restored.workbench.analyze_motion,Qt.MouseButton.LeftButton);QTest.qWait(20)
        assert restored.workbench.right_tabs.currentIndex()==0 and restored.intent_controller.note.isVisible()
        restored.close();QTest.qWait(30)
    write_json(proof/'acceptance.json',dict(passed=True,actual_qt=True,recognition='protocol fixture only',no_generation_submitted=True,
        checks=['canvas PNG/GIF/PNG sequence drops','no automatic analysis','explicit analysis','reference playback','clip slider',
                'source separation','no debug panel','left task footer','fixed positions','exclusive right tabs',
                'splitter resize/save','old layout migration','default reset','small screen']))
    print('AlI canvas drops / explicit analysis / fixed tabs / left task footer: PASS',flush=True)


if __name__=='__main__':main()
