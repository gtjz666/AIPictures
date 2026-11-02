import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog,QPushButton
from aipictures.app import Window,create_application
from aipictures.engine import ComfyClient
from aipictures.seed_controls import copy_seed
from aipictures.frame_selection import open_selection
from tests.test_manual_frames import fixture


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)),\
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        root=Path(temp);w=Window();w.timer.stop();w.show();QTest.qWait(20)
        assert w.seed_mode.currentData()=='random' and w.seed.text()=='-1'
        w.positive.setPlainText('紫发角色，白色上衣')
        w.generation_type.setCurrentIndex(1);assert not w.custom_description.isVisible()
        assert '紫发角色' in w.positive.toPlainText() and '交替' in w.positive.toPlainText()
        w.positive.setPlainText('角色平躺后翻滚，保持参考配色')
        w.connected=True;w.client=ComfyClient();w.animation_source.setCurrentIndex(1)
        with patch.object(w,'start_next'),patch('aipictures.video_controller.secrets.randbelow',side_effect=[101,102]):
            w.video_controller.intercept();w.video_controller.intercept()
        first,second=[entry[1] for entry in w.pending]
        assert [first['seed'],second['seed']]==[101,102]
        assert first['prompt']=='角色平躺后翻滚，保持参考配色' and first['action_description']==''
        assert first['prompt_layout']=='unified' and w.actual_seed.text()=='102'
        copy_seed(w);assert app.clipboard().text()=='102'
        next(b for b in w.findChildren(QPushButton) if b.text()=='复用').click()
        assert w.seed_mode.currentData()=='fixed' and w.seed.text()=='102'
        w.clear_pending();w.generation_type.setCurrentIndex(0)
        assert w.positive.toPlainText()=='紫发角色，白色上衣'
        w.generation_type.setCurrentIndex(1);assert '翻滚' in w.positive.toPlainText()
        manifest=fixture(root/'source');w.video_controller.player.load(manifest)
        player=w.video_controller.player;player.timer.stop();player.slider.setValue(8);player.advance()
        assert player.index==0 and player.loop.isChecked() and w.actual_seed.text()=='987654321'
        open_selection(w,manifest);picker=w.frame_selection_dialog;QTest.qWait(30)
        picker.copy_seed.click();assert app.clipboard().text()=='987654321'
        assert picker.selected()==[] and not picker.sheet_button.isEnabled()
        picker.seek(4);assert '第 5 / 9 帧' in picker.frame_label.text();picker.pick_current()
        picker.grid.item(1).setCheckState(Qt.CheckState.Checked);picker.grid.item(8).setCheckState(Qt.CheckState.Checked)
        assert picker.selected()==[1,4,8]
        picker.play(True);picker.timer.stop();picker.play_position=2;picker.advance();assert picker.index==1
        picker.transparent.setChecked(False)
        sheet=root/'chosen.png'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(sheet),'PNG')):picker.export('sheet')
        deadline=time.monotonic()+15
        while w.preparing and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
        assert not w.preparing and sheet.is_file(),picker.status.text()
        assert json.loads(sheet.with_suffix('.json').read_text())['source_indices']==[1,4,8]
        assert len(w.animation_player.frames)==3 and w.animation_player.preview_loop.isChecked()
        w.animation_player.slider.setValue(2);w.animation_player.advance();assert w.animation_player.index==0
        picker.close();app.processEvents();w.close()
    print('Unified prompt, random/fixed/actual seed, loop preview, manual pick and actual sheet export: PASS')


if __name__=='__main__':main()
