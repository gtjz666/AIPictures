"""Actual Qt export controls and Godot launch context, without model inference."""
import argparse,tempfile
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog,QFileDialog,QProgressBar,QPushButton
from aipictures.app import Window,create_application
from aipictures.godot_assets import install_addon
from aipictures.storage import write_json
from tools.verify_dock_workspace import wait_until


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof',type=Path);args=parser.parse_args()
    if args.proof:args.proof.mkdir(parents=True,exist_ok=True)
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
        root=Path(temp);project=root/'project';project.mkdir();(project/'project.godot').write_text('config_version=5\n')
        for target in ('aipictures.app.DATA','aipictures.storage.DATA'):stack.enter_context(patch(target,root/'data'))
        for method in ('auto_connect_engine','restore_chat','refresh_stats'):stack.enter_context(patch.object(Window,method))
        w=Window();stack.callback(lambda:(w.close(),QTest.qWait(40)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(40)
        for row in (w.task_display,w.export_tasks):
            assert row.isVisible() and row.percent.text()=='0%'
            assert row.layout().count()==3
        c=w.godot_controller;c.launch_context(project,'sfx')
        assert c.project==project and w.workbench.category=='audio' and w.audio_controller.kind.currentData()=='sfx'
        c.launch_context(project,'animation');assert w.generation_type.currentData()=='walk'
        frames=[]
        for i in range(8):
            p=root/f'{i}.png';Image.new('RGBA',(16,24),(i*20,70,90,255)).save(p);frames.append(p)
        d=c.frames(frames,8);d.preset.setCurrentIndex(d.preset.findData('four_way'))
        d.save();assert not w.preparing and '有效' in d.status.text()
        for row in range(4):d.ranges.cellWidget(row,1).setValue(row*2+1);d.ranges.cellWidget(row,2).setValue(row*2+2)
        d.export.click();wait_until(lambda:not w.export_tasks.busy)
        assert d.result and d.reveal.isEnabled() and Path(d.result['scene']).is_file(),d.status.text()
        assert w.task_display.started is None
        if args.proof:d.grab().save(str(args.proof/'export-dialog.png'))
        d.close();QTest.qWait(40)
        # Export selected frames as portable content through the actual Qt control.
        from aipictures.frame_selection import FrameSelectionDialog
        source=root/'sequence';source.mkdir()
        sequence=source/'sequence.json';write_json(sequence,dict(status='completed',fps=8,frames=[dict(image=str(p)) for p in frames]))
        picker=FrameSelectionDialog(w,sequence);picker.show()
        assert not picker.png_button.isEnabled() and not picker.sheet_button.isEnabled()
        for index in (5,2):picker.grid.item(index).setCheckState(Qt.CheckState.Checked)
        picker.transparent.setChecked(False)
        sheet=root/'walk.png'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(sheet),'PNG')):
            picker.sheet_button.click()
            popup=next(d for d in w.findChildren(QDialog) if d.windowTitle()=='正在导出')
            assert popup.isVisible() and not popup.findChildren(QProgressBar)
            assert any(button.text()=='取消导出' for button in popup.findChildren(QPushButton))
            wait_until(lambda:not w.export_tasks.busy)
        assert w.export_tasks.percent.text()=='100%'
        assert picker.reveal.isEnabled() and picker.output_path==sheet.resolve(),picker.status.text()
        metadata=json.loads(sheet.with_suffix('.json').read_text('utf-8'))
        assert metadata['sheet']==sheet.name and metadata['source_indices']==[2,5]
        with Image.open(sheet) as image:
            assert image.size==(32,24) and image.getpixel((16,0))==(100,70,90,255)
        assert sorted(p.name for p in root.glob('walk.*'))==['walk.json','walk.png']
        existing=root/'frame_000.png'
        existing.write_bytes(b'user-file')
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(root)):
            picker.png_button.click()
            assert not picker.png_button.isEnabled() and not picker.sheet_button.isEnabled()
            wait_until(lambda:not w.export_tasks.busy)
        sequence_folder=picker.output_path
        assert sequence_folder.parent==root.resolve() and existing.read_bytes()==b'user-file'
        assert sorted(p.name for p in sequence_folder.iterdir())==['animation.json','frame_000.png','frame_001.png']
        assert json.loads((sequence_folder/'animation.json').read_text('utf-8'))['source_indices']==[2,5]
        with Image.open(sheet) as atlas:
            for i,expected in enumerate((40,100)):
                with Image.open(sequence_folder/f'frame_{i:03d}.png') as image:
                    assert image.getpixel((0,0))==(expected,70,90,255)
                    assert image.tobytes()==atlas.crop((i*16,0,(i+1)*16,24)).tobytes()
        assert w.export_tasks.percent.text()=='100%' and picker.reveal.isEnabled()
        picker.close();QTest.qWait(40)
        application=root/'app';(application/'aipictures').mkdir(parents=True);(application/'aipictures/app.py').write_text('')
        python=application/'.venv/Scripts/python.exe';python.parent.mkdir(parents=True);python.write_bytes(b'installer-test-only')
        addon=install_addon(project,application);assert (addon/'plugin.cfg').exists()
        (addon/'plugin.gd').write_text('# user edit')
        install_addon(project,application)
        assert any(p.read_text('utf-8')=='# user edit' for p in (project/'.aipictures').glob('addon_backup_*/plugin.gd'))
        if args.proof:write_json(args.proof/'acceptance.json',dict(actual_qt=True,frames_exported=True,four_direction_mapping=True,portable_sprite_sheet=True,numbered_png_sequence=True,percentage_rows=True,export_popup_without_bar=True,project_launch_context=True,plugin_backup=True,model_inference=False))
    print('Qt Godot context / project component / PNG sequence / sprite sheet / safe install: PASS')


if __name__=='__main__':main()
