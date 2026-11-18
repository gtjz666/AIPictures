"""Exercise the real Qt player and deferred CPU export, with no model calls."""
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from aipictures.app import Window,create_application
from tools.verify_dock_workspace import wait_until
from tests.test_deferred_video import deferred


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)/'cache'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        root=Path(temp);w=Window();w.timer.stop();w.show();QTest.qWait(30)
        manifest,array=deferred(root/'source');player=w.video_controller.player
        player.load(manifest);player.timer.stop();player.slider.setValue(8)
        assert player.count==9 and not player.frames and player.index==8
        assert w.pixmap.toImage().pixelColor(0,0).getRgb()[:3]==tuple(array[8,0,0])
        assert not list(manifest.parent.rglob('*.png'))
        target=root/'export.mp4'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):
            player.save();wait_until(lambda:not w.export_tasks.busy)
        assert target.is_file() and not list(manifest.parent.rglob('*.png'))
        player.split()
        picker=w.frame_selection_dialog
        assert picker.source.count==9 and not list(manifest.parent.rglob('*.png'))
        picker.seek(8);picker.pick_current();picker.transparent.setChecked(False)
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(root)):
            picker.export('pngs');wait_until(lambda:not w.export_tasks.busy)
        exported=list(root.glob('frames_*/*.png'))
        assert len(exported)==1 and not list(manifest.parent.rglob('*.png'))
        from PIL import Image
        with Image.open(exported[0]) as image:
            assert image.convert('RGB').tobytes()==array[8].tobytes()
        w.close();QTest.qWait(30)
    print('Lazy exact-RGB preview / complete video / explicit frame export: PASS')


if __name__=='__main__':main()
