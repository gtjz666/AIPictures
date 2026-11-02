"""Actual Qt: keep Z-Image selected, freeze edits, and clear back to text-only."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock,patch

from PIL import Image
from PySide6.QtTest import QTest

from aipictures.app import Window,create_application
from aipictures.image_family import restore
from tests.test_zimage_reference import model_info


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)),patch('aipictures.storage.DATA',Path(temp)),\
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        root=Path(temp);w=Window();w.timer.stop();w.show();QTest.qWait(20)
        w.info={'object_info':model_info(),'nodes':list(model_info())};w.connected=True
        w.client=Mock(url='http://127.0.0.1:8189');w.client.upload_image.return_value='uploaded_frozen.png'
        restore(w);assert w.model_family.currentData()=='zimage'
        assert not w.reference_path and w.pixmap.isNull()
        source=root/'character.png';Image.new('RGBA',(500,900),(255,255,255,255)).save(source)
        before=source.read_bytes();w.set_reference(str(source))
        assert w.model_family.currentData()=='zimage' and w.model_family.model().item(1).isEnabled()
        assert w.preview_role=='reference' and not w.pixmap.isNull()
        w.open_settings('image');QTest.qWait(10)
        assert w.denoise.isVisible() and w.denoise.isEnabled() and w.denoise.value()==.45
        assert not w.reference_policy.isVisible() and not w.reference_strength.isVisible()
        w.reference_policy.setCurrentIndex(w.reference_policy.findData('preserve'))
        assert w.denoise.maximum()==1.  # Hidden SDXL policy must not clamp this engine.
        w.settings_dialogs['image'].hide()
        w.positive.setPlainText('保持参考角色，上衣改成蓝色');w.negative.setPlainText('水印')
        w.denoise.setValue(.65);w.seed.setText('1234')
        with patch.object(w,'start_next'):
            w.enqueue();w.positive.setPlainText('用于下次的新描述');w.denoise.setValue(.2)
            deadline=time.monotonic()+15
            while w.preparing or w.workers:
                app.processEvents();QTest.qWait(10)
                assert time.monotonic()<deadline
        assert len(w.pending)==1,w.chat.toPlainText()
        graph,params,folder,_=w.pending[0]
        assert params['model_family']=='zimage' and params['denoise']==.65
        assert params['user_prompt']=='保持参考角色，上衣改成蓝色' and params['seed']==1234
        assert graph['reference']['inputs']['image']=='uploaded_frozen.png'
        assert graph['sample']['inputs']['denoise']==.65 and graph['latent']['class_type']=='VAEEncode'
        assert source.read_bytes()==before
        w.clear_pending();w.clear_reference()
        assert w.model_family.currentData()=='zimage' and w.pixmap.isNull() and not w.reference_path
        graph,params=w.graph_snapshot()
        assert graph['latent']['class_type']=='EmptySD3LatentImage' and params['denoise']==1.
        assert not params['bindings']['reference'] and 'reference' not in graph
        w.set_reference(str(source));assert w.denoise.value()==.2  # Preserve user's last setting.
        assert w.generation_type.currentData()=='image'
        w.clear_reference();w.close();app.processEvents()
    print('Z-Image reference UI / frozen prompt and denoise / uploaded pixels / clear reference: PASS')


if __name__=='__main__':main()
