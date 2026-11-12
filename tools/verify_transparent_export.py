"""Real CPU matte: deferred RGB -> processed picker -> exact transparent/raw exports."""
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
from aipictures.frame_selection import FrameSelectionDialog
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
    app=create_application([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc');shown=[]
    def wait(condition,timeout=300):
        deadline=time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:app.processEvents();QTest.qWait(20)
        assert condition(),'Timed out waiting for export preparation'
    old_show=FrameSelectionDialog.show
    def show(dialog):
        for p in dialog.paths:
            with Image.open(p) as im:assert im.getchannel('A').getextrema()==(0,255)
        shown.append(True);return old_show(dialog)
    with patch('aipictures.app.DATA',root/'isolated'),patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'),patch('aipictures.background.MODEL',config['model']),patch('aipictures.background.MODEL_ROOT',Path(config['root'])),patch.object(FrameSelectionDialog,'show',show):
        w=Window();w.timer.stop();w.resize(1280,850);w.show();w.video_controller.player.load(manifest)
        w.video_controller.player.timer.stop();w.video_controller.player.split()
        wait(lambda:not w.preparing and getattr(w,'frame_selection_dialog',None) is not None)
        picker=w.frame_selection_dialog;assert shown and not picker.selected()
        assert not w.task_display.clock.isActive() and w.progress.value()==100
        for i,p in enumerate(picker.paths):
            with Image.open(p) as im:assert np.array_equal(np.array(im.convert('RGB')),images[i])
        derived=picker.manifest;meta=json.loads(derived.read_text('utf-8'));assert meta['export_background']['device']=='cpu'
        picker.check_all(True);picker.grab().save(str(root/'transparent-picker.png'))
        target=root/'sheet.png'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'PNG')):picker.export('sheet')
        wait(lambda:not w.preparing)
        assert target.is_file(),picker.status.text()
        export=json.loads(w.animation_player.manifest.read_text('utf-8'))
        with Image.open(target) as sheet:
            for row in export['frames']:
                with Image.open(w.animation_player.manifest.parent/row['image']) as im:
                    assert im.getchannel('A').getextrema()==(0,255)
            metadata=json.loads(target.with_suffix('.json').read_text('utf-8'))
            for row in metadata['frames']:
                r=row['rect']
                with Image.open(w.animation_player.manifest.parent/row['image']) as im:assert sheet.crop((r['x'],r['y'],r['x']+r['w'],r['y']+r['h'])).tobytes()==im.tobytes()
        picker.transparent.setChecked(False);picker.grab().save(str(root/'original-picker.png'))
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(root)):picker.export('pngs')
        wait(lambda:not w.preparing)
        raw_export=json.loads(w.animation_player.manifest.read_text('utf-8'))
        for i,p in enumerate(sorted(Path(raw_export['output']).glob('*.png'))):
            with Image.open(p) as im:assert im.getchannel('A').getextrema()==(255,255) and np.array_equal(np.array(im.convert('RGB')),images[i])
        picker.close();app.processEvents();w.video_controller.player.load(manifest);w.video_controller.player.timer.stop()
        with patch('aipictures.export_background.subprocess.Popen') as spawn:
            w.video_controller.player.split();wait(lambda:not w.preparing and getattr(w,'frame_selection_dialog',None) is not None)
            assert spawn.call_count==0
        w.frame_selection_dialog.close();w.close();app.processEvents()
    assert digest(rgb)==rgb_sha and all(digest(Path(p))==sha for p,sha in originals.items())
    write_json(root/'acceptance.json',dict(actual_qt=True,actual_cpu_model=True,new_ai_generation=False,input='Two actual generated RGB images in a deferred RGB-array fixture, not a new generated video.',rgba_before_dialog_shown=True,canvas_rgb_exact=True,raw_option_retained=True,sheet_readback_exact=True,reopen_without_worker=True,worker_exited=True,source_hashes=originals,derived_manifest=str(derived)))
    print('Real transparent export preparation and Qt flow: PASS')

if __name__=='__main__':main()
