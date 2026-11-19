import json
import tempfile
import time
from threading import Event
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog,QProgressDialog,QPushButton
from aipictures.app import Window,create_application
from aipictures.engine import ComfyClient
from aipictures.seed_controls import copy_seed
from aipictures.frame_selection import open_selection
from tests.test_manual_frames import fixture


def verify_parallel_export(w,app,root):
    import numpy as np
    from PIL import Image
    from aipictures.engine import Cancelled
    from aipictures.storage import write_json
    source=root/'native';source.mkdir()
    rgb=np.stack([np.full((12,16,3),color,dtype=np.uint8) for color in (40,80,120,160)])
    np.save(source/'rgb.npy',rgb)
    manifest=source/'video.json'
    write_json(manifest,dict(status='completed',frames=[],fps=24,frame_count=4,
              native_rgb_source=str(source/'rgb.npy')))
    w.task_display.start()
    w.progress.setRange(0,100);w.progress.setValue(100)
    assert w.progress.value()==99
    w.progress.setRange(0,0)
    assert w.progress.maximum()==100 and w.progress.value()==99
    generation_cancel=Event()
    w.current=dict(params={'mode':'video'},folder=root/'generation',cancel=generation_cancel)
    calls=[]
    entered=Event();release=Event()
    def matte(image,cancel,**_):
        calls.append(image.getpixel((0,0))[0])
        entered.set()
        if not release.wait(6):raise TimeoutError('Test export did not resume')
        if cancel.is_set():raise Cancelled('测试取消')
        image.putalpha(96)
        return image
    try:
        with patch('aipictures.background.foreground_rgba',side_effect=matte):
            picker=open_selection(w,manifest)
            assert picker and not calls and not picker.selected()
            assert not w.preparing and list(source.glob('*.png'))==[]
            for index in (1,3):picker.grid.item(index).setCheckState(Qt.CheckState.Checked)
            target=root/'parallel.png'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'PNG')):
                picker.export('sheet')
            deadline=time.monotonic()+5
            while not entered.is_set() and time.monotonic()<deadline:QTest.qWait(10)
            assert entered.is_set() and w.export_tasks.busy
            assert any(dialog.isVisible() for dialog in w.findChildren(QProgressDialog))
            assert w.current['cancel'] is generation_cancel and w.progress.value()==99
            assert w.export_tasks.cancel is not generation_cancel
            w.task_display.finish()
            w.progress.setRange(0,0);w.progress.setValue(70)
            assert w.progress.maximum()==100 and w.progress.value()==100
            release.set()
            deadline=time.monotonic()+5
            while w.export_tasks.busy and time.monotonic()<deadline:QTest.qWait(10)
        assert calls==[80,160] and target.is_file() and not generation_cancel.is_set()
        assert w.export_tasks.progress.value()==100 and w.progress.value()==100
        assert not list(source.glob('*.png'))
        assert json.loads(manifest.read_text('utf-8'))['frames']==[]
        with Image.open(target) as sheet:
            assert sheet.getpixel((0,0))==(80,80,80,96)
            assert sheet.getpixel((16,0))==(160,160,160,96)
        picker.close();app.processEvents()
    finally:
        release.set()
        w.current=None


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)),\
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'),\
         patch('aipictures.h3_backend.settings',return_value={'validated':True}):
        root=Path(temp);w=Window();w.timer.stop();w.show();QTest.qWait(20)
        assert w.seed_mode.currentData()=='random' and w.seed.text()=='-1'
        w.positive.setPlainText('紫发角色，白色上衣')
        # Templates are explicit choices; the new workbench defaults to free description.
        assert w.animation_action.currentData()=='custom'
        w.animation_action.setCurrentIndex(w.animation_action.findData('walk'))
        w.generation_type.setCurrentIndex(1);assert not w.custom_description.isVisible()
        assert not w.positive.toPlainText()  # Each mode starts with a manual prompt.
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
        open_selection(w,manifest)
        deadline=time.monotonic()+10
        while w.preparing and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
        picker=w.frame_selection_dialog;QTest.qWait(30)
        picker.copy_seed.click();assert app.clipboard().text()=='987654321'
        assert picker.selected()==[] and not picker.sheet_button.isEnabled()
        assert not picker.play_selected.isEnabled() and picker.selected_strip.isHidden() and picker.index is None
        picker.grid.item(4).setCheckState(Qt.CheckState.Checked)
        assert not picker.timer.isActive() and '所选第 1 / 1 帧 · 原第 5 帧' in picker.frame_label.text()
        picker.grid.item(1).setCheckState(Qt.CheckState.Checked);picker.grid.item(8).setCheckState(Qt.CheckState.Checked)
        assert picker.selected()==[1,4,8]
        assert [picker.selected_strip.item(i).data(Qt.ItemDataRole.UserRole) for i in range(3)]==[1,4,8]
        assert picker.timer.isActive() and picker.index==8 and '暂停' in picker.play_selected.text()
        picker.fps.setValue(10)
        assert picker.timer.interval()==100
        picker.advance();assert picker.index==1
        picker.advance();assert picker.index==4 and '所选第 2 / 3 帧' in picker.frame_label.text()
        picker.play_selected.click();assert not picker.timer.isActive()
        picker.selected_strip.itemClicked.emit(picker.selected_strip.item(2))
        assert picker.index==8 and '原第 9 帧' in picker.frame_label.text()
        picker.play_selected.click();picker.advance();assert picker.index==1
        picker.grid.item(1).setCheckState(Qt.CheckState.Unchecked)
        assert picker.index==4 and picker.selected_strip.count()==2
        picker.loop.setChecked(False)
        picker.advance();assert picker.index==8
        picker.advance();assert not picker.timer.isActive()
        picker.check_all(False)
        assert picker.index is None and picker.preview.pixmap().isNull()
        assert picker.selected_strip.isHidden() and not picker.play_selected.isEnabled()
        for index in (4,8):picker.grid.item(index).setCheckState(Qt.CheckState.Checked)
        picker.grid.item(1).setCheckState(Qt.CheckState.Checked)
        picker.loop.setChecked(True)
        picker.transparent.setChecked(False)
        sheet=root/'chosen.png'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(sheet),'PNG')):picker.export('sheet')
        deadline=time.monotonic()+15
        while w.export_tasks.busy and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
        assert not w.export_tasks.busy and sheet.is_file(),picker.status.text()
        assert json.loads(sheet.with_suffix('.json').read_text())['source_indices']==[1,4,8]
        assert len(w.animation_player.frames)==3 and w.animation_player.preview_loop.isChecked()
        w.animation_player.slider.setValue(2);w.animation_player.advance();assert w.animation_player.index==0
        picker.close();app.processEvents()
        verify_parallel_export(w,app,root)
        w.close()
    print('Unified prompt, random/fixed/actual seed, loop preview, manual pick and actual sheet export: PASS')


if __name__=='__main__':main()
