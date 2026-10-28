"""Real Qt drag -> saved character clip -> immutable queued workflow input; no test GPU job."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox
from aipictures.app import Window,create_application
from aipictures.storage import DATA,write_json
from aipictures.workflow_library import digest
from aipictures.animation_actions import ACTIONS


def main():
    app=create_application([])
    source=DATA/'references/be93d02d63944509ba617f5c90021bd0.png'
    with tempfile.TemporaryDirectory(dir=DATA) as directory:
        root=Path(directory)
        with patch('aipictures.app.DATA',root),patch('aipictures.motion_clip.DATA',root),patch.object(Window,'load_gallery'),patch.object(Window,'restore_chat'):
            w=Window(); w.show(); started=time.monotonic()
            while not w.connected and time.monotonic()-started<25: QTest.qWait(100)
            assert w.connected
            w.timer.stop(); w.generation_type.setCurrentIndex(1); w.set_reference(source)
            assert w.animation_engine.currentData()=='animate' and w.motion_mode.currentData()=='auto'
            assert w.animation_action.count()==5
            assert '左右腿交替' in w.positive.toPlainText()
            w.open_motion_editor(); started=time.monotonic()
            while not hasattr(w,'motion_dialog') and time.monotonic()-started<15: QTest.qWait(100)
            assert hasattr(w,'motion_dialog'),w.status.toolTip()
            dialog=w.motion_dialog; dialog.choice.setCurrentIndex(3); QTest.qWait(150)
            before=json.loads(json.dumps(dialog.motion)); joint=before['frames'][2]['joints']['right_wrist']
            rect=dialog.canvas.canvas_rect()
            point=QPoint(round(rect.x()+joint[0]*rect.width()/768),round(rect.y()+joint[1]*rect.height()/1024))
            QTest.mousePress(dialog.canvas,Qt.MouseButton.LeftButton,pos=point)
            QTest.mouseMove(dialog.canvas,point+QPoint(35,-15),delay=80)
            QTest.mouseRelease(dialog.canvas,Qt.MouseButton.LeftButton,pos=point+QPoint(35,-15))
            assert dialog.motion['edited']
            assert dialog.motion['frames'][2]['joints']['right_wrist']!=joint
            assert dialog.motion['frames'][3]==before['frames'][3]
            dialog.grab().save(str(DATA/'motion-editor-preview.png'))
            dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click(); QTest.qWait(80)
            assert w.motion_mode.currentData()=='manual'
            queued=root/'animations/queued'
            with patch('aipictures.walk_cycle.new_sequence',return_value=queued),patch.object(w,'start_next'):
                w.enqueue_walk()
            assert len(w.pending)==1,w.chat_messages[-1]
            params=w.pending[0][1]; item=w.pending[0][3]
            assert params['motion']['source_sha256']==digest(source)
            assert params['motion']['frames'][2]['joints']['right_wrist']!=joint
            assert item.text()=='走路动画 · 等待'
            w.current={'params':params}; w.status.setText('节点处理 abc123-12345678')
            assert w.status.text()=='走路动画'
            w.progress.setRange(0,100); w.progress.setValue(37)
            assert w.task_display.percent.text()=='37%'
            assert w.inspector.isAncestorOf(w.status) and w.inspector.isAncestorOf(w.progress)
            w.grab().save(str(DATA/'task-card-preview.png'))
            w.current=None; w.pending.clear()
            for action in ACTIONS:
                w.animation_action.setCurrentIndex(w.animation_action.findData(action))
                assert ACTIONS[action][1] in w.positive.toPlainText()
            while w.workers: QTest.qWait(80)
            w.close()
    write_json(DATA/'motion-editor-acceptance.json',{'passed':True,'real_joint_drag':True,
        'other_keyframes_unchanged':True,'saved_clip_bound_to_queue':True,'source_sha_checked':True,
        'automatic_full_cycle_default':True,'five_action_defaults':True,
        'task_name_and_percentage_together_on_left':True,'task_identifier_hidden':True})
    print('Motion editing, automatic action presets and left task card checks passed.',flush=True)


if __name__=='__main__': main()
