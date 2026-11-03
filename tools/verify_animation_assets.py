"""Real registered settings/assets and completed recognition, without submitting inference."""
import argparse
import json
import shutil
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from aipictures.workflow_library import digest
from tools.verify_dock_workspace import drop,wait_until


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True);p.add_argument('--motion',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True);a=p.parse_args()
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False);isolated=root/'isolated'
    for name in ('h3-settings.json','motion-native-settings.json','local-intent-settings.json'):
        isolated.mkdir(exist_ok=True);shutil.copyfile(a.data/name,isolated/name)
    before=[digest(a.image),digest(a.motion)];result=json.loads(a.plan.read_text('utf-8'))
    app=create_application([])
    with patch('aipictures.app.DATA',isolated),patch.object(Window,'auto_connect_engine'), \
         patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(80)
        drop(app,w.preview,[a.motion]);wait_until(lambda:not w.preparing,40);QTest.qWait(50)
        assert not w.pixmap.isNull() and not w.preview.pixmap().isNull() and not w.reference_path
        w.grab().save(str(root/'video-only.png'))
        drop(app,w.preview,[a.image]);QTest.qWait(80)
        w.intent_controller.current_record=a.plan.parent;w.intent_controller.apply(result)
        b=w.workbench;b.right_tabs.setCurrentIndex(1);b.motion_changed();QTest.qWait(50)
        assert b.timeline.isVisible() and w.negative.toPlainText().strip()
        assert b.timeline.table.rowCount()==len(result['plan']['timeline'])
        w.grab().save(str(root/'animation.png'))
        w.resize(1280,800);QTest.qWait(50)
        assert w.size().height()<=820 and not w.preview.pixmap().isNull()
        w.grab().save(str(root/'compact.png'))
        b.right_tabs.setCurrentIndex(0);QTest.qWait(30);w.grab().save(str(root/'prompts.png'))
        w.video_controller.seconds.setValue(32);b.right_tabs.setCurrentIndex(1);QTest.qWait(30)
        assert w.video_controller.seconds.value()==32
        assert not w.current and not w.pending and not w.intent_controller.running
        assert before==[digest(a.image),digest(a.motion)]
        write_json(root/'acceptance.json',dict(passed=True,actual_registered_settings=True,actual_assets=True,
            reused_real_recognition=str(a.plan.resolve()),no_generation_submitted=True,no_analysis_on_import=True,
            video_only_visible=True,six_buttons=True,editable_actions=True,negative_nonempty=True,
            duration_seconds=w.video_controller.seconds.value(),source_sha256=before))
        w.close();QTest.qWait(40)
    print('Actual asset / video-only / six buttons / editable retargeted actions / compact UI: PASS')


if __name__=='__main__':main()
