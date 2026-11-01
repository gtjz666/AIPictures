"""Exercise real Qt video preview, explicit extraction, and frozen queue settings."""
import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from aipictures.app import Window,create_application
from aipictures.result_cache import ResultCache
from aipictures.video_io import encode_pngs


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)),\
         patch.object(Window,'connect_engine'),patch.object(Window,'restore_chat'),\
         patch.object(Window,'refresh_stats'):
        root=Path(temp);window=Window();window.timer.stop();window.show();QTest.qWait(25)
        assert not window.reference_path and window.pixmap.isNull()
        assert not window.lora.isVisible() and not window.lora.isEnabled()
        window.generation_type.setCurrentIndex(1)
        controller=window.video_controller
        assert controller.free() and not window.research_bones_button.isVisible()
        window.animation_action.setCurrentIndex(window.animation_action.findData('run'))
        assert window.custom_description.toPlainText().strip()
        window.custom_description.setPlainText('转向正面，双手举起，再平躺在地上')
        window.animation_action.setCurrentIndex(window.animation_action.findData('jump'))
        assert '跳跃' in window.custom_description.toPlainText() and '平躺' not in window.custom_description.toPlainText()
        window.animation_action.setCurrentIndex(window.animation_action.findData('run'))
        assert '平躺' in window.custom_description.toPlainText()  # Restore this template's edited draft.
        from aipictures.engine import ComfyClient
        window.connected=True;window.client=ComfyClient();window.positive.setPlainText('蓝发角色');window.animation_source.setCurrentIndex(1)
        with patch.object(window,'start_next'):
            controller.intercept()
        _,params,folder,_=window.pending[-1]
        assert params['mode']=='video' and params['lora']=='' and params['reference'] is None
        assert '平躺' in params['action_description']
        window.positive.setPlainText('新内容');assert params['prompt']=='蓝发角色'
        window.clear_pending()
        assert json.loads((folder/'job.json').read_text('utf-8'))['kind']=='video'
        window.cache_store=ResultCache(root/'cache');folder=root/'cache/videos/preview';folder.mkdir(parents=True)
        frames=[]
        for i in range(9):
            path=folder/f'frame_{i}.png';Image.new('RGB',(64,96),(20,90+i,170)).save(path);frames.append(path)
        master=folder/'animation.mp4';encode_pngs(frames,master,24,threading.Event())
        manifest=folder/'video.json';manifest.write_text(json.dumps({'kind':'video','status':'completed',
            'source_video':str(master),'fps':24,'frames':[{'image':p.name} for p in frames],'sprites_created':False}))
        controller.player.load(manifest);controller.player.timer.stop()
        assert controller.player.isVisible() and len(controller.player.frames)==9
        assert window.preview_role=='video' and window.output is None
        controller.player.slider.setValue(8);assert controller.player.index==8 and '9/9' in controller.player.label.text()
        with patch('aipictures.video_import_dialog.open_import') as extract:
            controller.player.split();extract.assert_called_once_with(window,master)
        assert not (folder/'sequence.json').exists()
        saved=root/'export.mp4'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(saved),'')):
            controller.player.save()
        assert saved.read_bytes()==master.read_bytes()
        assert window.cache_store.saved_files()[0]['kind']=='video'
        window.animation_engine.setCurrentIndex(window.animation_engine.findData('animate'))
        assert not controller.free() and window.research_bones_button.isVisible()
        window.close()
    print('Full animation Qt preview / explicit split / no LoRA / frozen queue: PASS')


if __name__=='__main__':main()
