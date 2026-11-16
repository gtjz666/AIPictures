"""Actual Qt export controls and Godot launch context, without model inference."""
import argparse,tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtTest import QTest
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
        c=w.godot_controller;c.launch_context(project,'sfx')
        assert c.project==project and w.workbench.category=='audio' and w.audio_controller.kind.currentData()=='sfx'
        c.launch_context(project,'animation');assert w.generation_type.currentData()=='walk'
        frames=[]
        for i in range(8):
            p=root/f'{i}.png';Image.new('RGBA',(16,24),(i*20,70,90,255)).save(p);frames.append(p)
        d=c.frames(frames,8);d.preset.setCurrentIndex(d.preset.findData('four_way'))
        d.save();assert not w.preparing and '有效' in d.status.text()
        for row in range(4):d.ranges.cellWidget(row,1).setValue(row*2+1);d.ranges.cellWidget(row,2).setValue(row*2+2)
        d.export.click();wait_until(lambda:not w.preparing)
        assert d.result and d.drag.isEnabled() and d.drag.scene.is_file(),d.status.text()
        assert not w.task_display.clock.isActive()
        if args.proof:d.grab().save(str(args.proof/'export-dialog.png'))
        d.close();QTest.qWait(40)
        # Normal selected-frame export must open a usable child of the modal picker.
        from aipictures.frame_selection import FrameSelectionDialog
        sequence=root/'sequence.json';write_json(sequence,dict(status='completed',fps=8,frames=[dict(image=p.name) for p in frames]))
        picker=FrameSelectionDialog(w,sequence);picker.show();picker.check_all(True);picker.export_godot()
        assert c.dialog.parentWidget() is picker and c.dialog.isVisible();c.dialog.close();picker.close();QTest.qWait(40)
        application=root/'app';(application/'aipictures').mkdir(parents=True);(application/'aipictures/app.py').write_text('')
        python=application/'.venv/Scripts/python.exe';python.parent.mkdir(parents=True);python.write_bytes(b'installer-test-only')
        addon=install_addon(project,application);assert (addon/'plugin.cfg').exists()
        (addon/'plugin.gd').write_text('# user edit')
        install_addon(project,application)
        assert any(p.read_text('utf-8')=='# user edit' for p in (project/'.aipictures').glob('addon_backup_*/plugin.gd'))
        if args.proof:write_json(args.proof/'acceptance.json',dict(actual_qt=True,frames_exported=True,four_direction_mapping=True,draggable_scene=True,modal_child=True,project_launch_context=True,plugin_backup=True,model_inference=False))
    print('Qt Godot context / explicit presets / actual export / drag path / modal child / safe install: PASS')


if __name__=='__main__':main()
