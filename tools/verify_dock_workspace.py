"""Real Qt file drops, explicit analysis, fixed tabs and size persistence. No GPU."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData,QUrl
from PySide6.QtGui import QDragEnterEvent,QDropEvent,QEnterEvent
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
        assert w.editor._web is None and w.editor._profile is None
        assert b.canvas.x()<b.right_tabs.x() and b.right_tabs.count()==3
        assert [b.right_tabs.tabText(i) for i in range(3)]==['参考','动画','提示词']
        assert b.right_tabs.currentWidget()==b.reference_items
        assert not b.right_tabs.isMovable() and not b.workspace.childrenCollapsible()
        assert all(not dock.isVisible() for dock in w.findChildren(QDockWidget))
        assert b.task.parentWidget()==b.canvas
        assert not w.inspector.isVisible() and not w.output_shortcut.isEnabled()
        assert [a.text() for a in w.menuBar().actions()]==['记录','画面','采样','连接','API','窗口']
        assert all(not label.isVisible() for label in (w.creation_summary,w.reference_label,w.context_label,w.intent_hint,w.seed_notice))
        before=image.read_bytes(),gif.read_bytes();drop(app,w.preview,[image]);QTest.qWait(350)
        assert w.reference_path and Path(w.reference_path)!=image and w.preview_role is None
        assert b.reference_thumb.isVisible() and len(calls)==0 and not w.current and not w.pending
        assert b.right_tabs.currentIndex()==0 and not b.reference_item._pixmap.isNull()
        assert b.reference_thumb.mapTo(w,QPoint(0,0)).x()>b.right_tabs.mapTo(w,QPoint(0,0)).x()
        reference=w.reference_path;drop(app,w.preview,[gif]);wait_until(lambda:not w.preparing)
        QTest.qWait(300);panel=w.video_controller.motion
        assert w.reference_path==reference and panel.path and w.preview_role is None and len(calls)==0
        assert b.reference_player.isVisible() and b.reference_player.paths
        assert b.right_tabs.currentIndex()==0 and not b.motion_selection.isVisible() and not b.prompts.isVisible()
        assert b.motion_item.isVisible() and not panel.asset_header.isVisible()
        assert b.reference_items.isAncestorOf(b.motion_item) and b.reference_items.isAncestorOf(b.reference_item)
        assert not b.canvas.isAncestorOf(b.reference_item) and not w.attach_reference_button.isVisible()
        assert b.reference_item.mapTo(w,QPoint(0,0)).y()<b.motion_item.mapTo(w,QPoint(0,0)).y()
        # Both previews are independent from a generated still and generated animation.
        w.show_image(str(image));output_state=(w.output,w.preview_path,w.preview_role,w.pixmap.cacheKey())
        source_state=w.reference_path,panel.path,w.generation_type.currentData(),w.positive.toPlainText()
        QTest.mouseClick(b.reference_item,Qt.MouseButton.LeftButton)
        assert b.reference_note.full_text==image.name and b.reference_item.text()==''
        QTest.mouseClick(b.motion_item,Qt.MouseButton.LeftButton)
        assert b.reference_player.timer.isActive() and b.motion_note.full_text==gif.name
        assert (w.output,w.preview_path,w.preview_role,w.pixmap.cacheKey())==output_state and w.image_save.isEnabled()
        assert (w.reference_path,panel.path,w.generation_type.currentData(),w.positive.toPlainText())==source_state
        QTest.mouseClick(b.reference_player.play,Qt.MouseButton.LeftButton);assert not b.reference_player.timer.isActive()
        assert not b.reference_player.play.text() and b.reference_player.play.accessibleName()=='播放'
        assert not b.reference_player.play.icon().isNull()
        b.reference_player.slider.setValue(3)
        b.motion_item.setFocus();QTest.keyClick(b.motion_item,Qt.Key.Key_Space)
        assert b.reference_player.timer.isActive() and b.reference_player.slider.value()==3
        b.reference_player.toggle()
        generated=root/'sequence.json';write_json(generated,dict(status='completed',fps=12,frames=[dict(index=i,stage='test',image=str(image)) for i in range(2)]))
        w.animation_player.load(generated);assert w.animation_player.timer.isActive()
        assert not w.animation_player.play.text() and w.animation_player.play.accessibleName()=='暂停'
        b.reference_player.toggle();QTest.qWait(100)
        assert b.reference_player.play.accessibleName()=='暂停'
        assert w.preview_role=='animation' and w.animation_player.timer.isActive() and b.reference_player.timer.isActive()
        b.reference_player.toggle();assert w.animation_player.timer.isActive();w.animation_player.stop()
        b.reference_player.toggle();b.right_tabs.setCurrentIndex(2);QTest.qWait(100)
        assert not b.reference_player.timer.isActive(),'Hidden references must stop rendering.'
        assert b.prompts.isVisible() and not panel.isVisible() and c.role.isVisible()
        assert c.role.parentWidget()==w.positive.parentWidget()
        assert [c.role.itemData(i) for i in range(c.role.count())]==['appearance','style','custom']
        assert not c.role_note.isVisible()
        c.role.setCurrentIndex(2);assert c.role_note.isVisible()
        before_fingerprint=c.fingerprint();c.role_note.setText('只参考构图，替换人物与画风');assert c.fingerprint()!=before_fingerprint
        assert not calls,'Changing reference use must not invoke recognition.'
        w.positive.setPlainText('生成一张图');QTest.mouseClick(c.organize,Qt.MouseButton.LeftButton);wait_until(lambda:not c.running)
        assert calls[-1]['role']=='custom' and calls[-1]['reference_usage']=='只参考构图，替换人物与画风'
        c.role_note.clear();QTest.mouseClick(c.organize,Qt.MouseButton.LeftButton);assert not c.running and len(calls)==1
        c.role.setCurrentIndex(1);assert not c.role_note.isVisible()
        b.right_tabs.setCurrentIndex(1)
        assert all(not button.isVisible() for button in (panel.play,panel.add,panel.add_frames,panel.remove,b.remove_reference))
        assert not panel.range_button.isVisible() and not hasattr(b,'analyze_motion') and b.timeline.isVisible()
        panel.range_slider.setValue(min(500,panel.range_slider.maximum()));assert panel.start.value()>0
        w.positive.setPlainText('角色模仿参考动作')
        c.start(False);wait_until(lambda:not c.running)
        assert len(calls)==2 and calls[-1]['role']=='style' and calls[-1]['reference_usage']=='' and '抬手' in w.positive.toPlainText() and not c.note.isVisible()
        assert not c.intercept(),'Generation must not trigger another analysis.'
        assert not w.current and not w.pending and before==(image.read_bytes(),gif.read_bytes())
        # PNG sequence import keeps the still character reference separate.
        pngs=[]
        for i in (10,2):
            path=root/f'frame_{i}.png';Image.new('RGBA',(96,144),(i,20,180,255)).save(path);pngs.append(path)
        with patch('aipictures.intent_controller.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes), \
             patch('aipictures.intent_controller.QInputDialog.getInt',return_value=(24,True)):
            drop(app,w.preview,pngs);wait_until(lambda:not w.preparing)
        QTest.qWait(300);assert panel.path.suffix=='.json' and w.reference_path==reference and len(calls)==2
        assert b.plan is None and b.timeline.rows()==[],'No inferred timeline may populate the manual grid.'
        assert b.motion_item.isVisible() and b.motion_item.accessibleName()=='参考动画'
        # A folder needs neither a file picker nor a confirmation dialog.
        folder=root/'ordered-frames';folder.mkdir()
        for index in (10,1,2):Image.new('RGBA',(96,144),(index,20,180,255)).save(folder/f'frame_{index}.png')
        write_json(folder/'sprite_sheet.json',dict(fps=12))
        with patch('aipictures.intent_controller.QMessageBox.question',side_effect=AssertionError('Unexpected folder confirmation')), \
             patch('aipictures.intent_controller.QInputDialog.getInt',side_effect=AssertionError('Unexpected folder FPS dialog')):
            drop(app,b.motion_item,[folder]);wait_until(lambda:not w.preparing)
        QTest.qWait(60)
        mapping=json.loads((panel.path.parent/'source-map.json').read_text('utf-8'))
        assert [r['source'] for r in mapping]==['frame_1.png','frame_2.png','frame_10.png']
        assert panel.meta['frame_fps']==12 and b.motion_note.full_text==folder.name and w.reference_path==reference
        assert b.reference_player.timer.isActive()
        assert not hasattr(b,'analysis_tabs')
        panel.range_slider.setValue(1);QTest.qWait(20)
        assert '2/3' in panel.start_note.text() and b.reference_player.index==1
        original_prompt=w.positive.toPlainText()
        b.right_tabs.setCurrentIndex(1)
        with patch('aipictures.local_intent.analyze_frame',return_value=dict(frame_analysis=dict(index=1,time=1/12,description='第2帧主体抬手'),engine_released=True)) as inspect_frame:
            c.start(False,frame_only=True)
            inspect_frame.assert_not_called();assert not c.running and not hasattr(b,'frame_review')
        assert w.positive.toPlainText()==original_prompt
        b.right_tabs.setCurrentIndex(1)
        assert panel.frame_rate_row.isVisible();panel.frame_rate.setValue(24);panel.frame_rate.editingFinished.emit()
        wait_until(lambda:not w.preparing);assert panel.meta['frame_fps']==24
        b.right_tabs.setCurrentIndex(0)
        QTest.mouseClick(b.reference_item,Qt.MouseButton.LeftButton)
        w.show_image(str(image));output_state=(w.output,w.preview_path,w.preview_role,w.pixmap.cacheKey())
        point=QPoint(b.motion_item.width()-10,4);global_point=b.motion_item.mapToGlobal(point)
        app.sendEvent(b.motion_item,QEnterEvent(QPointF(point),QPointF(w.mapFromGlobal(global_point)),QPointF(global_point)))
        assert b.motion_item.close_button.isVisible()
        QTest.mouseClick(b.motion_item.close_button,Qt.MouseButton.LeftButton)
        assert panel.path is None and w.reference_path==reference and b.motion_item._pixmap.isNull()
        assert (w.output,w.preview_path,w.preview_role,w.pixmap.cacheKey())==output_state
        # Removing the still while a motion is present keeps the other source available.
        drop(app,w.preview,[gif]);wait_until(lambda:not w.preparing);QTest.qWait(40)
        QTest.mouseClick(b.reference_item,Qt.MouseButton.LeftButton)
        point=QPoint(b.reference_item.width()-10,4);global_point=b.reference_item.mapToGlobal(point)
        app.sendEvent(b.reference_item,QEnterEvent(QPointF(point),QPointF(w.mapFromGlobal(global_point)),QPointF(global_point)))
        QTest.mouseClick(b.reference_item.close_button,Qt.MouseButton.LeftButton)
        assert panel.path and not b.motion_item._pixmap.isNull() and b.reference_item._pixmap.isNull()
        assert b.remove_reference.isEnabled()
        b.close_asset('motion')
        assert not panel.path and not b.remove_reference.isEnabled()
        assert (w.output,w.preview_path,w.preview_role,w.pixmap.cacheKey())==output_state
        assert not b.source_note.full_text
        w.resize(1280,800);QTest.qWait(40)
        assert w.size().height()<=820,'References must also fit the compact layout.'
        w.resize(1440,940);QTest.qWait(30)
        w.status.setText('已导出 1 帧：C:\\temporary\\sprite.png');w.progress.setValue(100)
        assert 'temporary' not in w.status.text() and not w.task_display.detail.isVisible() and b.task.height()<110
        w.grab().save(str(proof/'workspace.png'))
        assert b.task.mapTo(w,QPoint(0,0)).x()+b.task.width()<=b.canvas.mapTo(w,QPoint(0,0)).x()+b.canvas.width()+2
        b.workspace.setSizes([760,540]);b.prompt_splitter.setSizes([240,160]);b.right_tabs.setCurrentIndex(2)
        b.save_layout();saved=json.loads((root/'cache/workspace-layout.json').read_text('utf-8'))
        assert saved['schema_version']==3 and saved['right_tab']=='prompts'
        ratio=saved['columns'][0]/sum(saved['columns'])
        w.close();QTest.qWait(40)
        restored=Window();restored.timer.stop();restored.show();QTest.qWait(70)
        sizes=restored.workbench.workspace.sizes()
        assert abs(sizes[0]/sum(sizes)-ratio)<.05 and restored.workbench.right_tabs.currentIndex()==0
        # Saved sizes survive, but startup always opens references in both formats.
        for old_index,key in enumerate(('prompts','animation','reference')):
            write_json(root/'cache/workspace-layout.json',dict(saved,schema_version=2,right_tab=old_index))
            restored.workbench.restore_layout()
            assert restored.workbench.right_tabs.currentWidget()==restored.workbench.reference_items
        for key in ('prompts','animation','reference'):
            write_json(root/'cache/workspace-layout.json',dict(saved,right_tab=key))
            restored.workbench.restore_layout()
            assert restored.workbench.right_tabs.currentWidget()==restored.workbench.reference_items
        restored.workbench.reset_layout();QTest.qWait(60)
        assert restored.workbench.canvas.x()<restored.workbench.right_tabs.x() and restored.workbench.right_tabs.currentIndex()==0
        restored.resize(1280,800);QTest.qWait(40);assert restored.size().height()<=820
        restored.grab().save(str(proof/'compact.png'))
        restored.workbench.right_tabs.setCurrentIndex(1);restored.positive.clear()
        restored.intent_controller.start(False);QTest.qWait(20)
        assert restored.workbench.right_tabs.currentIndex()==2 and restored.intent_controller.note.isVisible()
        assert restored.editor._web is None
        restored.editor.connect_url('http://127.0.0.1:9',load=False)
        assert restored.editor._web is None
        restored.editor.ensure_browser();assert restored.editor._web is not None and restored.editor.page is not None
        restored.close();QTest.qWait(30)
    write_json(proof/'acceptance.json',dict(passed=True,actual_qt=True,recognition='protocol fixture only',no_generation_submitted=True,
        checks=['canvas PNG/GIF/PNG sequence drops','no automatic analysis','explicit analysis','reference playback','clip slider',
                'source separation','no debug panel','left task footer','fixed positions','exclusive right tabs',
                'splitter resize/save','old layout migration','default reset','small screen']))
    print('AlI canvas drops / explicit analysis / fixed tabs / left task footer: PASS',flush=True)


if __name__=='__main__':main()
