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
        for i in range(128):
            p=root/f'{i}.png';Image.new('RGB',(96,144),(30+i,50,160)).save(p);paths.append(p)
        clip=root/'motion.mp4';encode_pngs(paths,clip,24,threading.Event())
        w=Window();w.timer.stop();w.resize(1280,800);w.show();QTest.qWait(100)
        b=w.workbench;vc=w.video_controller
        drop(app,w.preview,[clip]);wait_until(lambda:not w.preparing);QTest.qWait(100)
        assert w.reference_path is None and b.right_tabs.currentIndex()==0 and w.pixmap.isNull()
        assert not b.motion_item._pixmap.isNull() and b.reference_player.isVisible()
        b.right_tabs.setCurrentIndex(1)
        assert b.analyze_motion.isVisible() and not vc.motion.range_button.isVisible()
        assert not w.animation_action.isVisible() and not b.creation_kind.model().item(1).isEnabled()
        assert not w.intent_controller.running and not w.current
        assert b.timeline_region.isVisible() and not b.timeline.isVisible()
        assert b.timeline_region.height()>=200 and b.animation_header.height()<270
        assert not vc.motion.play.isVisible()
        assert not b.motion_item._pixmap.isNull() and not vc.motion.asset_header.isVisible()
        assert b.motion_item.isAncestorOf(b.motion_item.thumb)
        vc.motion.range_slider.setValue(4500)
        wait_until(lambda:vc.motion.preview_offset>=4.49)
        assert w.preview_role is None and not b.motion_item._pixmap.isNull()
        vc.motion.range_slider.setValue(0);wait_until(lambda:vc.motion.preview_offset==0)
        w.grab().save(str(proof/'before-analysis.png'))
        vc.seconds.setValue(32);assert vc.seconds.value()==8
        vc.seconds.setValue(4)
        positive='角色保持蓝色衣服。\n从0秒开始：抬手(0.0s)→收手(0.1s)'
        result=dict(plan=dict(kind='animation',positive_prompt=positive,timeline=[dict(start=0,end=.1,description='抬手'),dict(start=.1,end=.333,description='收手')]))
        w.positive.setPlainText(positive);b.show_plan(result)
        assert '从0秒开始' not in w.positive.toPlainText() and '蓝色衣服' in w.positive.toPlainText()
        assert b.timeline.isVisible() and b.timeline.table.rowCount()==2
        table=b.timeline.table;table.setItem(0,2,QTableWidgetItem('右手向镜头挥拳'))
        w.positive.setPlainText(w.positive.toPlainText()+'\n\n保留水彩线条。')
        table.setItem(0,2,QTableWidgetItem('右手向镜头挥拳'))
        assert w.positive.toPlainText().count('以下为可编辑动作时间线')==1 and '保留水彩线条。' in w.positive.toPlainText()
        assert '右手向镜头挥拳' in w.positive.toPlainText() and b.timeline.rows()[0]['description']=='右手向镜头挥拳'
        vc.seconds.setValue(48);assert b.timeline.rows()[-1]['end']<=8
        assert b.timeline.rows()[0]['description']=='右手向镜头挥拳'
        vc.seconds.setValue(4);assert b.timeline.rows()[-1]['end']<=4
        table.setItem(0,0,QTableWidgetItem('NaN'))
        try:b.timeline.rows();raise AssertionError('Invalid timing accepted')
        except ValueError:pass
        table.setItem(0,0,QTableWidgetItem('0'))
        vc.h3={'validated':True};vc.motion_settings={'validated':True}
        # The actual controller must freeze edited rows into the queued job.
        with patch.object(vc,'enqueue') as enqueue:
            assert vc.intercept();wait_until(lambda:not w.preparing)
            assert enqueue.call_args.args[0]['motion_timeline'][0]['description']=='右手向镜头挥拳'
            assert enqueue.call_args.args[0]['motion_timeline_clock']=='output'
            assert all(0<=r['start']<r['end']<=4 for r in enqueue.call_args.args[0]['motion_timeline'])
        vc.motion.start.setValue(.5)
        try:b.timeline.effective_rows();raise AssertionError('Stale source window entered queue')
        except ValueError as exc:assert '重新分析' in str(exc)
        vc.motion.start.setValue(0)
        # A long, looping source must not contribute future actions to a 4s output.
        vc.motion.repeat.setChecked(True)
        scoped=dict(plan=dict(kind='animation',positive_prompt='保持蓝色衣服。',timeline=[
            dict(start=0,end=2,description='抬手'),dict(start=2,end=4,description='收手'),
            dict(start=4,end=vc.motion.meta['duration'],description='跳跃')]))
        w.positive.setPlainText(scoped['plan']['positive_prompt']);b.show_plan(scoped)
        assert b.timeline.rows()==[dict(start=0.,end=2.,description='抬手'),dict(start=2.,end=4.,description='收手')]
        assert '跳跃' not in w.positive.toPlainText() and '参考素材秒数' not in w.positive.toPlainText()
        b.timeline.table.setItem(0,2,QTableWidgetItem('右手挥向镜头'))
        vc.seconds.setValue(6);assert b.timeline.rows()[0]['description']=='右手挥向镜头'
        assert b.timeline.rows()[-1]['end']==6
        vc.seconds.setValue(4);assert b.timeline.rows()[-1]['end']==4
        w.positive.setPlainText('用户重新写的动作：向左走。')
        assert not b.timeline.effective_rows(),'Manual prompt replacement must not retain a hidden old timeline.'
        # A splitter resize must refresh the actual left preview, not just the Window.
        b.workspace.setSizes([650,550]);QTest.qWait(50)
        assert b.motion_item.thumb.pixmap().width()<=b.motion_item.thumb.width()*b.motion_item.thumb.devicePixelRatioF()+2
        w.grab().save(str(proof/'editor.png'))
        vc.motion.clear();assert not b.timeline.isVisible() and not b.timeline.rows()
        QTest.qWait(40)
        assert b.timeline_region.isVisible() and b.timeline_region.height()>=200 and b.animation_header.height()<270
        w.close();QTest.qWait(40)
    write_json(proof/'acceptance.json',dict(passed=True,actual_qt=True,no_inference=True,video_only=True,editable_queue=True))
    print('Animation editor / independent reference / duration / editable queued timeline: PASS')


if __name__=='__main__':main()
