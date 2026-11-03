"""Actual Qt composer -> local model -> editable prompts; no diffusion submission."""
import argparse
import json
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from aipictures.app import Window, create_application
from aipictures.local_intent import settings
from aipictures.storage import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--resume', action='store_true', help='Reuse completed recognition after a presentation-only failure')
    args=parser.parse_args(); output=args.output.resolve()
    if output.exists() and not args.resume: raise ValueError('输出目录已经存在，请使用新目录。')
    previous = sorted(output.glob('intent/*/plan.json')) if args.resume else []
    if args.resume and (not previous or (output/'acceptance.json').exists()):
        raise ValueError('没有可恢复的识别结果，或验收已成功。')
    config=settings(args.data, require_validated=False)
    if not config: raise ValueError('需要已下载并校验的本地模型。')
    config=dict(config,validated=True)
    write_json(output/'local-intent-settings.json',config)
    app=create_application([])
    with patch('aipictures.app.DATA',output), patch.object(Window,'auto_connect_engine'), \
         patch.object(Window,'refresh_stats'), patch.object(Window,'restore_chat'):
        w=Window();w.timer.stop();w.resize(1440,900);w.show();QTest.qWait(30)
        c=w.intent_controller
        assert c.config and c.enabled.isChecked() and not w.reference_path
        w.positive.setPlainText('制作一个红色玻璃药水瓶，俯视角，放在深色木桌上，写实游戏道具图标。只要一个瓶子，不要人物，不要文字。')
        if previous:
            c.current_record=previous[-1].parent
            c.apply(json.loads(previous[-1].read_text('utf-8')))
        else:
            QTest.mouseClick(c.organize,Qt.MouseButton.LeftButton)
            deadline=time.monotonic()+120
            while c.running and time.monotonic()<deadline:QTest.qWait(30)
        assert not c.running and c.applied_context and not w.current and not w.pending,c.note.text()
        result=json.loads((c.current_record/'plan.json').read_text('utf-8'))
        assert result['engine_released'] and result['route']=='zimage'
        assert '红色' in w.positive.toPlainText() and '俯视' in w.positive.toPlainText()
        assert not c.intercept()
        w.grab().save(str(output/'workbench.png'))
        w.resize(1280,800);QTest.qWait(30)
        assert w.size().height()<=820,'The workbench must fit a smaller screen.'
        w.grab().save(str(output/'compact.png'))
        w.open_settings('sampling');QTest.qWait(30)
        assert w.seed_mode.isVisible()
        w.workbench.settings.grab().save(str(output/'settings.png'));w.workbench.settings.close()
        write_json(output/'acceptance.json',dict(passed=True,actual_qt=True,actual_local_model=True,
            generation_submitted=False,plan=str(c.current_record/'plan.json'),engine_released=result['engine_released'],
            elapsed_seconds=result['elapsed_seconds'],reused_completed_recognition=bool(previous)))
        w.close();QTest.qWait(50)
    print('Actual Qt -> Qwen3-VL -> editable prompts, released engine, compact layout: PASS',flush=True)


if __name__=='__main__':main()
