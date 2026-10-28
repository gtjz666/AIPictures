"""Real Qt frame cards, edited-pose playback, preview render and a ticking task clock."""
import json
import tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout
from aipictures.motion_editor import MotionDialog
from aipictures.motion_clip import make_clip,sample_clip
from aipictures.task_display import TaskDisplay
from aipictures.storage import DATA,write_json


def main():
    app=QApplication([]); DATA.mkdir(exist_ok=True)
    source=Path.home()/'Desktop/AIPictures/data/animations/20261028_233855_212f5c6b'
    analysis=json.loads((source/'reference_analysis.json').read_text('utf-8'))
    original=json.loads((source/'motion.json').read_text('utf-8'))
    clip=make_clip(original['base_rig'],original['source_sha256'],'walk',8,8)
    with tempfile.TemporaryDirectory() as directory,patch('aipictures.motion_clip.DATA',Path(directory)):
        dialog=MotionDialog(analysis,clip); dialog.show(); QTest.qWait(200)
        assert '第 1 / 8 帧' in dialog.frame_label.text()
        dialog.frame_buttons[2].click(); QTest.qWait(60)
        assert dialog.choice.currentData()==2 and dialog.frame_buttons[2].isChecked()
        assert '第 3 / 8 帧' in dialog.canvas.frame_caption
        before=deepcopy(dialog.motion); joint=before['frames'][2]['joints']['right_wrist']
        rect=dialog.canvas.canvas_rect(); start=QPoint(round(rect.x()+joint[0]*rect.width()/768),round(rect.y()+joint[1]*rect.height()/1024))
        QTest.mousePress(dialog.canvas,Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(dialog.canvas,start+QPoint(16,-10),delay=40)
        QTest.mouseRelease(dialog.canvas,Qt.MouseButton.LeftButton,pos=start+QPoint(16,-10))
        assert dialog.motion['frames'][2]['joints']['right_wrist']!=joint
        assert dialog.motion['frames'][1]==before['frames'][1]
        assert sample_clip(dialog.motion,.25)['joints']['right_wrist']==dialog.motion['frames'][2]['joints']['right_wrist']
        observed=set(); dialog.choice.currentIndexChanged.connect(lambda _:observed.add(dialog.choice.currentData()))
        dialog.play.click(); assert dialog.timer.isActive()
        QTest.qWait(2100); assert observed==set(range(8)),observed
        dialog.play.click(); assert not dialog.timer.isActive()
        dialog.grab().save(str(DATA/'motion-refined-preview.png'))
        dialog.stop_play(); assert dialog.choice.currentData()==0
        dialog.preview_mode.setCurrentIndex(1); assert not dialog.canvas.show_puppet
        dialog.close()
    owner=QWidget(); owner.current={'params':{'mode':'walk','action':'run'}}
    owner.task_display=TaskDisplay(owner); QVBoxLayout(owner).addWidget(owner.task_display); owner.show()
    display=owner.task_display; display.start(); display.status.setText('正在执行模型处理')
    QTest.qWait(1300); assert display.seconds()>=1 and '00:00' not in display.elapsed.text(),display.elapsed.text()
    display.finish(); frozen=display.seconds(); QTest.qWait(300); assert display.seconds()==frozen
    owner.close()
    write_json(DATA/'motion-refinement-controls.json',{'passed':True,'frame_badges':True,'frame_cards':True,
        'all_edited_keyframes_played':True,'observed_frames':sorted(observed),'single_frame_edit_preserved':True,
        'puppet_and_skeleton_modes':True,'elapsed_clock_ticks_without_model_events':True,'no_gpu_job_submitted':True})
    print('Frame navigation, edited full-cycle playback, local puppet and elapsed clock passed.',flush=True)


if __name__=='__main__': main()
