"""Actual Qt routing: validated native image editing and H3 without legacy fallback."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from aipictures.app import Window, create_application
from aipictures.image_family import restore
from tests.test_image_choice_retirement import model_info


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)),\
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),\
         patch.object(Window,'refresh_stats'),patch('aipictures.h3_backend.settings',return_value={'validated':True}):
        root=Path(temp);w=Window();w.timer.stop();w.show();QTest.qWait(20)
        (root/'flux-klein-settings.json').write_text(json.dumps({'validated':True}))
        from aipictures.engine import ComfyClient
        w.info={'object_info':model_info()};w.connected=True;w.client=ComfyClient()
        restore(w)
        assert w.model_family.currentData()=='flux_klein'
        w.positive.setPlainText('红色玻璃药水瓶，俯视图');w.negative.setPlainText('文字，水印')
        w.width.setValue(1024);w.height.setValue(1024)
        graph,params=w.graph_snapshot()
        assert params['model_family']=='flux_klein' and not params['bindings']['reference']
        assert graph['clip']['inputs']['type']=='flux2' and not w.translate_prompt.isVisible()
        assert not w.reference_strength.isVisible() and not w.cfg.isVisible()
        assert not w.denoise.isVisible() and not w.quality_mode.isVisible()
        source=root/'ref.png';Image.new('RGBA',(500,900),(80,120,180,255)).save(source)
        before=source.read_bytes();w.set_reference(str(source))
        assert w.preview_role is None and w.pixmap.isNull() and not w.workbench.reference_item._pixmap.isNull()
        assert w.width.value()%16==0 and w.height.value()%16==0
        graph,params=w.graph_snapshot('uploaded.png')
        assert graph['reference']['inputs']['image']=='uploaded.png'
        assert params['reference_policy']=='semantic' and params['reference_strength'] is None
        assert source.read_bytes()==before
        w.clear_reference();assert not w.reference_path and w.pixmap.isNull()
        assert w.model_family.currentData()=='flux_klein'
        w.generation_type.setCurrentIndex(1)
        assert w.animation_engine.count()==1 and w.animation_engine.currentData()=='h3'
        assert not w.research_bones_button.isVisible() and not w.custom_settings.isVisible()
        assert not any(b.text()=='应用已有角色基准' for b in w.findChildren(QPushButton))
        w.positive.setPlainText('角色转身后挥手');w.animation_source.setCurrentIndex(1)
        with patch.object(w,'start_next'):
            w.video_controller.intercept()
        params=w.pending[-1][1]
        assert params['engine']=='h3' and params['backend']=='standalone' and params['reference'] is None
        w.clear_pending();w.video_controller.h3={};w.video_controller.apply_ui()
        assert not w.generate_button.isEnabled() and '尚未安装' in w.intent_hint.text()
        try:w.video_controller.intercept()
        except ValueError as exc:assert '不会切回' in str(exc)
        else:raise AssertionError('Missing H3 incorrectly fell back to old engine')
        assert not w.pending
        w.close();app.processEvents()
    print('Validated image route / reference preview / H3 only / no fallback: PASS')


if __name__=='__main__':main()
