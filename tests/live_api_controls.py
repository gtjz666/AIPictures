"""Actual Qt widgets + HTTP test provider; never contacts real paid services."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtTest import QTest

from aipictures.app import Window, create_application
from aipictures.api_config import Endpoint
from aipictures.result_cache import ResultCache


def wait_for(predicate,seconds=8):
    deadline = time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        QTest.qWait(20)
        time.sleep(.01)  # Let Python HTTP worker acquire the GIL between Qt event pumps.
    assert predicate(),'Qt task did not finish in time'


def main(url):
    app = create_application([])
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        with patch('aipictures.app.DATA',root),patch.object(Window,'connect_engine') as connect,\
             patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
            window = Window(); window.timer.stop()
            window.cache_store = ResultCache(root)
            controller = window.api_controller
            controller.open_settings()
            dialog = controller.dialog
            assert dialog.fields['image']['key'].echoMode()==dialog.fields['image']['key'].EchoMode.Password
            dialog.backend.setCurrentIndex(1)
            values = dialog.fields['image']
            values['url'].setText(url+'/v1')
            values['model'].setEditText('image-test-model')
            dialog.save()
            assert not controller.cloud  # Missing Key must not enable cloud mode.
            values['key'].setText('fake-test-key-no-account')
            dialog.save()
            assert controller.cloud and window.generate_button.isEnabled() and not window.connected
            window.auto_connect_engine(); connect.assert_not_called()
            assert not window.cfg.isEnabled() and not window.lora.isEnabled() and not window.seed.isEnabled()
            window.output_background.setCurrentIndex(window.output_background.findData('preserve'))
            window.positive.setPlainText('俯视木箱，蓝色水彩')
            window.workbench.prompt_output.setPlainText('俯视木箱，蓝色水彩')
            # Real controller, worker, transport, image decode, cache, preview and gallery.
            window.enqueue()
            wait_for(lambda:window.current is None)
            jobs = sorted((root/'jobs').iterdir())
            assert len(jobs)==1
            job = json.loads((jobs[0]/'job.json').read_text('utf-8'))
            assert job['status']=='completed',job
            assert window.gallery.count()==1 and not window.pixmap.isNull()
            assert window.positive.toPlainText()=='俯视木箱，蓝色水彩'
            assert window.progress.value()==100 and '云端' in window.status.text()
            assert 'fake-test-key-no-account' not in ''.join(p.read_text('utf-8') for p in root.rglob('*.json'))
            # A queued job retains its reference + options when the UI changes.
            source = root/'original.png'; Image.new('RGBA',(12,14),(20,40,70,255)).save(source)
            values['edits'].setChecked(True); dialog.save()
            with patch.object(window,'start_next'):
                window.set_reference(source)
                window.workbench.prompt_output.setPlainText('俯视木箱，蓝色水彩')
                window.enqueue()
                graph,params,folder,item = window.pending[-1]
                assert Path(params['reference']).read_bytes()==source.read_bytes()
                window.clear_reference(); window.positive.setPlainText('完全不同的场景')
                assert params['user_prompt']=='俯视木箱，蓝色水彩' and Path(params['reference']).is_file()
                window.clear_pending()
                assert not controller.runtime
                assert json.loads((folder/'job.json').read_text('utf-8'))['status']=='cancelled'
            # Cancel and close an API job must never contact an existing ComfyUI client.
            window.client = Mock()
            window.workbench.prompt_output.setPlainText('完全不同的场景')
            window.enqueue()
            ticket = window.current
            window.cancel_current()
            assert ticket['cancel'].is_set()
            window.client.cancel.assert_not_called(); window.client.active_prompts.assert_not_called()
            wait_for(lambda:window.current is None)
            # Incompatible animation fails explicitly, without an invisible cloud call.
            window.generation_type.setCurrentIndex(1)
            count = len(list((root/'jobs').iterdir()))
            window.enqueue()
            assert len(list((root/'jobs').iterdir()))==count
            window.generation_type.setCurrentIndex(0)
            dialog.backend.setCurrentIndex(0); dialog.save()
            assert not controller.cloud and window.seed.isEnabled()
            assert not window.cfg.isEnabled()  # Native automatic routes use the model's fixed CFG.
            assert not window.generate_button.isEnabled()  # Local still requires connection.
            window.close(); QTest.qWait(30)
            # Corrupt configuration does not prevent launching the local app.
            (root/'api-settings.json').write_text('{invalid',encoding='utf-8')
            other = Window(); other.timer.stop()
            assert other.api_controller.load_error and not other.api_controller.cloud
            other.close()
    print('Qt API controls, real test HTTP, gallery, reference snapshot, cancel and fallback: PASS')


if __name__=='__main__':
    main(sys.argv[1])
