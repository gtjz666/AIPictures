"""Actual Qt automatic routing, frozen queues, missing-model gate and SDXL retirement."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtTest import QTest

from aipictures.app import Window, create_application
from aipictures.image_family import restore
from tests.test_image_choice_retirement import model_info as flux_info
from tests.test_zimage_reference import model_info as z_info


def main():
    app = create_application([])
    with tempfile.TemporaryDirectory() as tmp, patch('aipictures.app.DATA', Path(tmp)), \
         patch('aipictures.storage.DATA', Path(tmp)), patch.object(Window, 'auto_connect_engine'), \
         patch.object(Window, 'restore_chat'), patch.object(Window, 'refresh_stats'):
        root = Path(tmp)
        (root/'flux-klein-settings.json').write_text(json.dumps({'validated':True}))
        (root/'image-family.json').write_text(json.dumps({'family':'sdxl'}))
        info = z_info()
        for node, value in flux_info().items():
            if node in ('UNETLoader','CLIPLoader','VAELoader'):
                for field, spec in value['input']['required'].items():
                    info[node]['input']['required'][field][0].extend(n for n in spec[0]
                        if n not in info[node]['input']['required'][field][0])
            else: info[node] = value
        w=Window();w.timer.stop();w.show();QTest.qWait(20)
        w.info={'object_info':info,'nodes':list(info)};w.connected=True
        w.client=Mock(url='http://127.0.0.1:8189');w.client.upload_image.return_value='frozen_upload.png'
        restore(w)
        assert w.model_family.currentData()=='auto' and w.model_family.findData('sdxl')==-1
        assert 'Z-Image' in w.context_label.text()
        w.positive.setPlainText('黄色怪兽，梦核风格');w.seed.setText('9876')
        graph,params=w.graph_snapshot()
        assert params['model_family']=='zimage' and params['image_route']=='auto'
        assert graph['latent']['class_type']=='EmptySD3LatentImage' and not params['bindings']['reference']
        source=root/'ref.png';Image.new('RGBA',(500,900),(255,220,40,255)).save(source)
        before=source.read_bytes();w.set_reference(str(source))
        assert w.model_family.currentData()=='auto' and 'FLUX' in w.context_label.text()
        assert not w.denoise.isEnabled() and w.preview_role is None and not w.workbench.reference_item._pixmap.isNull()
        with patch.object(w.editor,'load_graph') as loaded:
            w.load_draft_in_editor()
            deadline=time.monotonic()+20
            while w.preparing or w.workers:
                app.processEvents();QTest.qWait(10)
                if time.monotonic()>=deadline:
                    import faulthandler
                    faulthandler.dump_traceback()
                    raise AssertionError(f'draft timeout preparing={w.preparing} workers={len(w.workers)} chat={w.chat.toPlainText()}')
            draft=loaded.call_args.args[0]
            assert draft['reference']['inputs']['image']=='frozen_upload.png'
            assert draft['latent']['class_type']=='EmptyFlux2LatentImage'
            assert draft['guider']['inputs']['positive']==['pos_ref',0]
        with patch.object(w,'start_next'):
            w.workbench.prompt_output.setPlainText('黄色怪兽，梦核风格')
            w.enqueue();w.clear_reference();w.positive.setPlainText('下一张背景图')
            deadline=time.monotonic()+15
            while w.preparing or w.workers:
                app.processEvents();QTest.qWait(10)
                assert time.monotonic()<deadline
        assert len(w.pending)==1,w.chat.toPlainText()
        graph,params,folder,_=w.pending[0]
        assert params['image_route']=='auto' and params['model_family']=='flux_klein'
        assert params['user_prompt']=='黄色怪兽，梦核风格' and params['seed']==9876
        assert graph['reference']['inputs']['image']=='frozen_upload.png'
        assert graph['latent']['class_type']=='EmptyFlux2LatentImage'
        assert graph['guider']['inputs']['positive']==['pos_ref',0]
        graph,params=w.graph_snapshot()
        assert params['model_family']=='zimage' and graph['latent']['class_type']=='EmptySD3LatentImage'
        assert 'reference' not in graph and 'FLUX' not in w.context_label.text()
        w.clear_pending();assert before==source.read_bytes()
        (root/'flux-klein-settings.json').unlink()
        w.set_reference(str(source));assert not w.generate_button.isEnabled()
        assert w.model_family.currentData()=='auto' and '缺失' in w.model_note.text()
        try:w.graph_snapshot('upload.png')
        except ValueError as exc:assert '验证' in str(exc)
        else:raise AssertionError('Missing FLUX silently fell back')
        w.model_family.setCurrentIndex(w.model_family.findData('zimage'))
        assert w.denoise.isEnabled() and w.generate_button.isEnabled()
        try:w.activate_template({'loader':{'class_type':'CheckpointLoaderSimple','inputs':{}}},'old')
        except ValueError as exc:assert '退役' in str(exc)
        else:raise AssertionError('Retired SDXL was activated')
        w.close();app.processEvents()
    print('Automatic Z/FLUX routing, frozen reference, missing-model gate, SDXL retired: PASS')


if __name__=='__main__':main()
