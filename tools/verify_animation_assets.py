"""Real registered settings/assets and completed recognition, without submitting inference."""
import argparse
import json
import shutil
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from aipictures.workflow_library import digest
from tools.verify_dock_workspace import drop,wait_until


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True);p.add_argument('--motion',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--generated',type=Path,help='Existing completed video.json; not regenerated')
    p.add_argument('--frames',type=Path);p.add_argument('--frame-analysis',type=Path);a=p.parse_args()
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False);isolated=root/'isolated'
    for name in ('h3-settings.json','motion-native-settings.json','local-intent-settings.json'):
        isolated.mkdir(exist_ok=True);shutil.copyfile(a.data/name,isolated/name)
    before=[digest(a.image),digest(a.motion)];result=json.loads(a.plan.read_text('utf-8'))
    app=create_application([])
    with patch('aipictures.app.DATA',isolated),patch.object(Window,'auto_connect_engine'), \
         patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(80)
        drop(app,w.preview,[a.motion]);wait_until(lambda:not w.preparing,40);QTest.qWait(50)
        assert w.pixmap.isNull() and not w.workbench.motion_item._pixmap.isNull() and not w.reference_path
        w.grab().save(str(root/'video-only.png'))
        drop(app,w.preview,[a.image]);QTest.qWait(80)
        w.intent_controller.current_record=a.plan.parent;w.intent_controller.apply(result)
        b=w.workbench;b.motion_changed();b.right_tabs.setCurrentIndex(1);QTest.qWait(50)
        assert b.timeline.isVisible() and w.negative.toPlainText().strip()
        assert b.timeline.table.rowCount()==len(result['plan']['timeline'])
        assert not w.video_controller.motion.asset_header.isVisible()
        assert b.reference_item.text()==b.motion_item.text()==''
        if a.generated:w.video_controller.player.load(a.generated)
        result_role=w.preview_role;result_manifest=w.video_controller.player.manifest
        b.right_tabs.setCurrentIndex(0);QTest.qWait(30)
        drop(app,b.reference_item,[a.image]);QTest.qWait(30)
        assert w.preview_role==result_role and w.video_controller.player.manifest==result_manifest
        if a.generated:
            assert w.video_controller.player.timer.isActive() and not w.video_controller.player.play.text()
        QTest.mouseClick(b.motion_item,Qt.MouseButton.LeftButton);QTest.qWait(100)
        assert b.reference_player.timer.isActive() and b.motion_note.full_text==a.motion.name
        w.grab().save(str(root/'animation.png'))
        QTest.mouseClick(b.reference_item,Qt.MouseButton.LeftButton);QTest.qWait(30)
        assert w.preview_role==result_role and b.reference_player.timer.isActive() and b.reference_note.full_text==a.image.name
        assert w.video_controller.player.manifest==result_manifest
        if a.generated:assert w.video_controller.player.timer.isActive()
        w.grab().save(str(root/'reference.png'))
        QTest.mouseClick(b.motion_item,Qt.MouseButton.LeftButton);QTest.qWait(30)
        w.resize(1280,800);QTest.qWait(50)
        assert w.size().height()<=820 and not b.motion_item._pixmap.isNull()
        w.grab().save(str(root/'compact.png'))
        b.right_tabs.setCurrentIndex(2);QTest.qWait(30);w.grab().save(str(root/'prompts.png'))
        c=w.intent_controller;c.role.setCurrentIndex(c.role.findData('custom'))
        c.role_note.setText('只参考黑白服装配色和细描边，主体换成机器人，不参考发型与站姿')
        QTest.qWait(30);assert c.role.isVisible() and c.role_note.isVisible()
        w.grab().save(str(root/'custom-purpose.png'))
        w.video_controller.seconds.setValue(32);b.right_tabs.setCurrentIndex(1);QTest.qWait(30)
        assert w.video_controller.seconds.value()==8
        assert not w.current and not w.pending and not w.intent_controller.running
        assert before==[digest(a.image),digest(a.motion)]
        if a.frames:
            drop(app,w.preview,[a.frames]);wait_until(lambda:not w.preparing,40);QTest.qWait(60)
            panel=w.video_controller.motion
            assert panel.is_frames() and b.analysis_tabs.currentIndex()==1
            panel.range_slider.setValue(1);QTest.qWait(30)
            assert b.reference_player.index==1 and panel.start_note.text().startswith('起始帧 2/')
            if a.frame_analysis:
                frame_result=json.loads(a.frame_analysis.read_text('utf-8'))
                assert digest(panel.preview_paths[1])==frame_result['frame_sha256']
                b.show_frame_analysis(frame_result);assert b.frame_review.table.rowCount()==1
            # Dispatch the hover event through Qt even when another desktop app
            # owns foreground focus; a native cursor move can go to that app.
            b.right_tabs.setCurrentIndex(0)
            point=QPoint(b.motion_item.width()-10,4);global_point=b.motion_item.mapToGlobal(point)
            app.sendEvent(b.motion_item,QEnterEvent(QPointF(point),QPointF(w.mapFromGlobal(global_point)),QPointF(global_point)))
            QTest.qWait(30);assert b.motion_item.close_button.isVisible()
            w.grab().save(str(root/'frame-references.png'))
            b.right_tabs.setCurrentIndex(1);QTest.qWait(30)
            w.grab().save(str(root/'frame-content.png'))
        write_json(root/'acceptance.json',dict(passed=True,actual_registered_settings=True,actual_assets=True,
            reused_real_recognition=str(a.plan.resolve()),no_generation_submitted=True,no_analysis_on_import=True,
            independent_reference_preview=True,generated_result_preserved=True,reference_uses=['appearance','style','custom'],
            animation_buttons=['分析动作'],editable_actions=True,negative_nonempty=True,
            duration_seconds=w.video_controller.seconds.value(),source_sha256=before))
        w.close();QTest.qWait(40)
    print('Actual assets / independent references / generated result retained / custom purpose / compact UI: PASS')


if __name__=='__main__':main()
