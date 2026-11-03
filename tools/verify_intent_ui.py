"""Real Qt interaction smoke test. Protocol fixture is not a model quality test."""
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from aipictures.app import Window, create_application
from aipictures.storage import write_json


def main():
    app = create_application([])
    output = Path('data/acceptance/intent-ui').resolve(); output.mkdir(parents=True, exist_ok=True)
    root = output/'isolated'; root.mkdir(exist_ok=True)
    png = root/'source.png'; Image.new('RGBA', (120, 180), (150, 100, 210, 255)).save(png)
    plan = dict(kind='image', summary='红色玻璃药水瓶，俯视，保留用户排除项。', positive_prompt='A single red glass potion bottle, top view, no lettering.',
                negative_prompt='watermark, text', observations=[], timeline=[], questions=[])
    result = dict(schema_version=1, plan=plan, route='zimage', elapsed_seconds=.25, model='protocol fixture',
                  engine_released=True, status='ready')
    calls = []
    def recognize(config, brief, negative, reference, motion, folder, cancel, emit, **kwargs):
        calls.append(dict(brief=brief, negative=negative, reference=reference, motion=motion, **kwargs))
        emit('intent_stage', {'message':'正在整理测试需求…'})
        write_json(folder/'plan.json', result)
        return result
    with patch('aipictures.app.DATA', root), patch.object(Window,'auto_connect_engine'), \
         patch.object(Window,'refresh_stats'), patch.object(Window,'restore_chat'), \
         patch('aipictures.intent_controller.settings', return_value={'name':'protocol fixture'}), \
         patch('aipictures.intent_controller.analyze', side_effect=recognize):
        w = Window(); w.timer.stop(); w.resize(1440, 940); w.show(); QTest.qWait(40)
        c = w.intent_controller
        assert c.enabled.isChecked() and not w.workbench.prompts.isVisible()
        assert set(w.workbench.sections)=={'creation','image','sampling','connection'}
        c.input.setPlainText('制作一个红色玻璃药水瓶，俯视，不要文字。')
        QTest.mouseClick(c.organize, Qt.MouseButton.LeftButton)
        deadline = time.monotonic()+8
        while c.running and time.monotonic()<deadline: QTest.qWait(20)
        assert not c.running and len(calls)==1
        assert w.positive.toPlainText()==plan['positive_prompt'] and w.workbench.prompts.isVisible()
        assert not c.intercept()
        w.positive.setPlainText('User-edited top view bottle')
        assert not c.intercept(), 'Manual prompt edits must not be rewritten.'
        c.input.setPlainText('制作蓝色玻璃药水瓶')
        with patch.object(c,'start') as start:
            assert c.intercept(); start.assert_called_once_with(True)
        w.grab().save(str(output/'image.png'))
        w.open_settings('creation'); QTest.qWait(40)
        assert w.workbench.settings.isVisible() and w.workbench.tabs.currentIndex()==0
        assert w.video_controller.seconds.parentWidget() is not None
        w.workbench.settings.grab().save(str(output/'settings.png')); w.workbench.settings.close()
        # Real import freezes source and displays it; defer automatic fixture planning.
        c.enabled.setChecked(False)
        before = png.read_bytes(); c.import_files([png]); QTest.qWait(20)
        assert w.reference_path and Path(w.reference_path)!=png and png.read_bytes()==before
        assert w.preview_role=='reference' and not w.pixmap.isNull()
        QTest.mouseClick(w.workbench.modes[1], Qt.MouseButton.LeftButton)
        assert w.generation_type.currentData()=='walk' and w.video_controller.motion.isVisible()
        animation = dict(result, plan=dict(plan, kind='animation', timeline=[{'start':0.,'end':.4,'description':'抬手并挥向镜头。'}]))
        c.apply(animation); w.workbench.show_plan(animation); QTest.qWait(25)
        assert w.animation_action.currentData()=='custom'
        w.workbench.show_timeline(); QTest.qWait(25)
        w.workbench.timeline_dialog.grab().save(str(output/'timeline.png')); w.workbench.timeline_dialog.close()
        w.grab().save(str(output/'animation.png'))
        c.running=True; w.preparing=True
        w.cancel_current(); assert c.cancel_event.is_set()
        c.running=False; w.preparing=False
        w.close(); QTest.qWait(30)
    write_json(output/'acceptance.json', dict(passed=True, actual_qt=True, recognition='protocol fixture only',
        checks=['compose','strict mode selection','reviewed edits','settings hub','reference freeze/preview','timeline','cancel']))
    print('Actual Qt composer / prompt edits / settings / references / timeline / cancel: PASS', flush=True)


if __name__=='__main__': main()
