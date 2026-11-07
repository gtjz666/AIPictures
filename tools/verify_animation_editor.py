"""Actual Qt manual action grid, prompt sync and queue snapshot. No model calls."""
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTableWidgetItem,QPushButton
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from aipictures.video_io import encode_pngs
from tools.verify_dock_workspace import drop,wait_until


def main():
    app=create_application([]);proof=Path('data/acceptance/manual-motion-editor-20261107/ui').resolve()
    proof.mkdir(parents=True,exist_ok=True);calls=[]
    def organize(*args,**kwargs):
        calls.append(kwargs)
        # An old/nonconforming model response must never populate the grid.
        return dict(plan=dict(kind='animation',positive_prompt='蓝色机器人，保留水彩线条。',negative_prompt='身份突变',
            summary='仅界面协议检查',observations=[],questions=[],timeline=[dict(start=0,end=99,description='错误自动动作')]))
    with tempfile.TemporaryDirectory() as temporary,patch('aipictures.app.DATA',Path(temporary)/'cache'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
         patch('aipictures.intent_controller.settings',return_value={'name':'protocol fixture'}), \
         patch('aipictures.intent_controller.analyze',side_effect=organize):
        root=Path(temporary);paths=[]
        for i in range(128):
            p=root/f'{i}.png';Image.new('RGB',(96,144),(30+i,50,160)).save(p);paths.append(p)
        clip=root/'motion.mp4';encode_pngs(paths,clip,24,threading.Event())
        w=Window();w.timer.stop();w.resize(1360,900);w.show();QTest.qWait(80)
        b=w.workbench;vc=w.video_controller;t=b.timeline;c=w.intent_controller
        vc.h3={'validated':True};vc.motion_settings={'validated':True}
        b.right_tabs.setCurrentWidget(b.animation)
        assert t.isVisible() and t.rows()==[] and t.table.rowCount()==1
        assert not any(button.text()=='分析动作' for button in w.findChildren(QPushButton))
        assert not hasattr(b,'frame_review') and not hasattr(b,'analysis_tabs')
        w.grab().save(str(proof/'empty-table.png'))
        drop(app,w.preview,[clip]);wait_until(lambda:not w.preparing)
        assert not calls and not w.intent_controller.running and not w.current
        assert w.reference_path is None and w.pixmap.isNull() and not b.motion_item._pixmap.isNull()
        assert b.right_tabs.currentWidget()==b.reference_items
        vc.seconds.setValue(4);w.positive.setPlainText('蓝色机器人，跟随参考动画。')
        # Generate without ever organizing prompts or analyzing the motion.
        with patch.object(vc,'enqueue') as enqueue:
            assert vc.intercept();wait_until(lambda:not w.preparing)
            frozen=enqueue.call_args.args[0]
            assert frozen['motion_timeline']==[] and '时间线' not in frozen['prompt']
            assert frozen['motion_prompt_policy']=='reference_first_manual_v2'
        b.right_tabs.setCurrentWidget(b.animation)
        t.table.setItem(0,0,QTableWidgetItem('1.0'))
        t.table.setItem(0,1,QTableWidgetItem('2.0'))
        t.table.setItem(0,2,QTableWidgetItem('右手向镜头挥拳'))
        assert t.rows()==[dict(start=1.,end=2.,description='右手向镜头挥拳')]
        assert t.table.rowCount()==2 and w.positive.toPlainText().count('用户修改的动作时间线')==1
        assert '1.000–2.000秒：右手向镜头挥拳' in w.positive.toPlainText()
        # Source selection changes do not invalidate output-time custom actions.
        vc.motion.start.setValue(.5);vc.motion.repeat.setChecked(True)
        assert t.effective_rows()[0]['start']==1 and not t.error.isVisible()
        vc.seconds.setValue(6);assert t.rows()[0]['end']==2
        vc.seconds.setValue(4);assert t.rows()[0]['end']==2
        with patch.object(vc,'enqueue') as enqueue:
            assert vc.intercept();wait_until(lambda:not w.preparing)
            frozen=enqueue.call_args.args[0]
            assert frozen['motion_timeline']==t.rows() and frozen['motion_timeline_clock']=='output'
            assert frozen['prompt']==w.positive.toPlainText().strip()
        # Invalid output times and partial rows stop queueing before file creation.
        t.table.setItem(0,1,QTableWidgetItem('9'))
        with patch.object(vc,'new_folder') as create:
            try:vc.intercept();raise AssertionError('Out-of-range custom time entered queue')
            except ValueError:pass
            create.assert_not_called()
        t.table.setItem(0,1,QTableWidgetItem('2'))
        t.table.setItem(1,0,QTableWidgetItem('3'))
        with patch.object(vc,'new_folder') as create:
            try:vc.intercept();raise AssertionError('Partial custom row entered queue')
            except ValueError:pass
            create.assert_not_called()
        t.table.selectRow(1);QTest.mouseClick(t.remove,Qt.MouseButton.LeftButton)
        assert t.rows()[0]['description']=='右手向镜头挥拳'
        # The prompt action is beside the purpose selector, with a separate style.
        b.right_tabs.setCurrentWidget(b.prompt_page);QTest.qWait(30)
        role_point=c.role.mapTo(w,QPoint(0,0));button_point=c.organize.mapTo(w,QPoint(0,0))
        assert button_point.x()>=role_point.x()+c.role.width() and abs(button_point.y()-role_point.y())<8
        assert c.organize.parentWidget()==w.positive.parentWidget() and c.organize.objectName()=='promptGenerate'
        QTest.mouseClick(c.organize,Qt.MouseButton.LeftButton);wait_until(lambda:not c.running)
        assert len(calls)==1 and calls[0]['describe_motion'] is False
        assert t.rows()[0]['description']=='右手向镜头挥拳' and '右手向镜头挥拳' in w.positive.toPlainText()
        assert '错误自动动作' not in w.positive.toPlainText() and len(t.rows())==1
        assert '蓝色机器人，保留水彩线条。' in w.positive.toPlainText()
        assert w.positive.toPlainText().count('用户修改的动作时间线')==1
        w.grab().save(str(proof/'prompt-actions.png'))
        c.start(False,motion_detail=True);c.start(False,frame_only=True)
        assert len(calls)==1 and not c.running
        # An incomplete table edit during a slow prompt request must invalidate
        # that result even though the last valid prompt footer has not changed.
        release=threading.Event();before=w.positive.toPlainText()
        def slow_organize(*args,**kwargs):
            assert release.wait(10)
            return organize(*args,**kwargs)
        with patch('aipictures.intent_controller.analyze',side_effect=slow_organize):
            c.start(False);assert c.running
            t.table.setItem(t.table.rowCount()-1,0,QTableWidgetItem('3'))
            release.set();wait_until(lambda:not c.running)
        assert w.positive.toPlainText()==before and '输入已修改' in c.note.text()
        t.table.selectRow(t.table.rowCount()-1);QTest.mouseClick(t.remove,Qt.MouseButton.LeftButton)
        # Purpose and reference changes preserve manual rows and reach the job.
        w.set_reference(str(paths[0]))
        for role in ('appearance','style','custom'):
            c.role.setCurrentIndex(c.role.findData(role))
            c.role_note.setText('只借用衣服颜色' if role=='custom' else '')
            with patch.object(vc,'enqueue') as enqueue:
                assert vc.intercept();wait_until(lambda:not w.preparing)
                assert enqueue.call_args.args[0]['reference_role']==role
                assert enqueue.call_args.args[0]['motion_timeline']==t.rows()
        c.role_note.clear()
        with patch.object(vc,'new_folder') as create:
            try:vc.intercept();raise AssertionError('Empty custom use entered queue')
            except ValueError:pass
            create.assert_not_called()
        # Clearing/replacing the prompt cannot resurrect an invisible old table.
        w.positive.setPlainText('用户重新写的动作：向左走。')
        assert t.generation_input()==('用户重新写的动作：向左走。',[])
        vc.seconds.setValue(6);assert w.positive.toPlainText()=='用户重新写的动作：向左走。'
        # The next explicit table edit attaches the custom table again.
        t.table.setItem(0,2,QTableWidgetItem('右手缓慢挥向镜头'))
        assert '右手缓慢挥向镜头' in w.positive.toPlainText() and '用户重新写的动作' in w.positive.toPlainText()
        b.right_tabs.setCurrentWidget(b.animation);w.grab().save(str(proof/'custom-table.png'))
        t.table.selectRow(0);QTest.mouseClick(t.remove,Qt.MouseButton.LeftButton)
        assert not t.rows() and '用户修改的动作时间线' not in w.positive.toPlainText()
        vc.motion.clear();assert t.isVisible() and not t.rows()
        # Text-only animation still accepts optional manual actions.
        t.table.setItem(0,0,QTableWidgetItem('0'));t.table.setItem(0,1,QTableWidgetItem('1'))
        t.table.setItem(0,2,QTableWidgetItem('向左走'))
        vc.seconds.setValue(4);w.clear_reference()
        with patch.object(vc,'enqueue') as enqueue:
            assert vc.intercept()
            assert enqueue.call_args.args[0]['motion_timeline'][0]['description']=='向左走'
            assert 'motion_reference' not in enqueue.call_args.args[0]
        w.close();QTest.qWait(40)
    write_json(proof/'acceptance.json',dict(passed=True,actual_qt=True,no_inference=True,
        default_empty_grid=True,custom_queue=True,optional_prompt_generation=True,automatic_analysis_removed=True))
    print('Manual actions / no motion analysis / prompt sync / queue / adjacent controls: PASS')


if __name__=='__main__':main()
