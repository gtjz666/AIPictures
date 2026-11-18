"""Real CPU matte: preview original RGB, then prepare only the frames selected for export."""
import argparse,json,os,time
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from PySide6.QtGui import QFontDatabase
from aipictures.app import Window,create_application
from aipictures.workflow_library import digest
from aipictures.storage import write_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof',type=Path,required=True);parser.add_argument('--images',type=Path,nargs=2,required=True);parser.add_argument('--data',type=Path,required=True);a=parser.parse_args()
    root=a.proof.resolve();root.mkdir(parents=True,exist_ok=False);source=root/'source';source.mkdir()
    originals={str(p.resolve()):digest(p) for p in a.images}
    images=[]
    for p in a.images:
        with Image.open(p) as im:images.append(np.array(im.convert('RGB')))
    assert images[0].shape==images[1].shape
    rgb=source/'frames.npy';np.save(rgb,np.stack(images));rgb_sha=digest(rgb)
    manifest=source/'video.json';write_json(manifest,dict(status='completed',fps=24,frames=[],frame_count=2,native_rgb_source=str(rgb),params=dict(seed=1739142441399876)))
    config=json.loads((a.data/'background-settings.json').read_text('utf-8'))
    from aipictures import background
    app=create_application([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    def wait(condition,timeout=300):
        deadline=time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:app.processEvents();QTest.qWait(20)
        assert condition(),'Timed out waiting for export preparation'
    with patch('aipictures.app.DATA',root/'isolated'),patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'),patch('aipictures.background.MODEL',config['model']),patch('aipictures.background.MODEL_ROOT',Path(config['root'])),patch.object(background,'foreground_rgba',wraps=background.foreground_rgba) as matte:
        w=Window();w.timer.stop();w.resize(1280,850);w.show();w.video_controller.player.load(manifest)
        w.video_controller.player.timer.stop();w.video_controller.player.split()
        picker=w.frame_selection_dialog;assert not picker.selected() and matte.call_count==0
        assert not w.export_tasks.busy and not list(source.glob('*.png'))
        assert np.array_equal(np.array(picker.source.image(1).convert('RGB')),images[1])
        picker.seek(1);picker.pick_current();picker.grab().save(str(root/'frame-picker.png'))
        target=root/'sheet.png'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'PNG')):picker.export('sheet')
        wait(lambda:not w.export_tasks.busy)
        assert target.is_file(),picker.status.text()
        assert matte.call_count==1 and w.export_tasks.progress.value()==100
        derived=picker.exported_manifest
        export=json.loads(derived.read_text('utf-8'));assert export['source_indices']==[1]
        with Image.open(target) as sheet:
            for row in export['frames']:
                with Image.open(derived.parent/row['image']) as im:
                    assert im.getchannel('A').getextrema()==(0,255)
            metadata=json.loads(target.with_suffix('.json').read_text('utf-8'))
            for row in metadata['frames']:
                r=row['rect']
                with Image.open(derived.parent/row['image']) as im:assert sheet.crop((r['x'],r['y'],r['x']+r['w'],r['y']+r['h'])).tobytes()==im.tobytes()
        picker.transparent.setChecked(False);picker.grab().save(str(root/'original-picker.png'))
        picker.check_all(True)
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(root)):picker.export('pngs')
        wait(lambda:not w.export_tasks.busy)
        raw_export=json.loads(picker.exported_manifest.read_text('utf-8'))
        for i,p in enumerate(sorted(Path(raw_export['output']).glob('*.png'))):
            with Image.open(p) as im:assert im.getchannel('A').getextrema()==(255,255) and np.array_equal(np.array(im.convert('RGB')),images[i])
        picker.close();app.processEvents();w.video_controller.player.load(manifest);w.video_controller.player.timer.stop()
        w.video_controller.player.split()
        assert w.frame_selection_dialog is not None and matte.call_count==1
        w.frame_selection_dialog.close();w.close();app.processEvents()
    assert digest(rgb)==rgb_sha and all(digest(Path(p))==sha for p,sha in originals.items())
    write_json(root/'acceptance.json',dict(actual_qt=True,actual_cpu_model=True,new_ai_generation=False,transparent_frames_processed=1,canvas_rgb_exact=True,raw_option_retained=True,sheet_readback_exact=True,reopen_without_worker=True,worker_exited=True,source_hashes=originals,derived_manifest=str(derived)))
    print('Real selected-frame CPU matte and Qt export: PASS')

if __name__=='__main__':main()
