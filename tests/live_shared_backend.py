"""Real Qt + live Comfy frontend; no GPU inference or user history mutations."""
import json
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.backend_connection import shared_backend_url
from aipictures.storage import DATA,write_json
from aipictures.workflow import ImageRequest,build_workflow


def main():
    app=create_application([]); expected=shared_backend_url('http://127.0.0.1:8188')
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        root=Path(temp);write_json(root/'settings.json',{'url':'http://127.0.0.1:8188'})
        with patch('aipictures.app.DATA',root),patch.object(Window,'load_gallery',lambda self:None),patch.object(Window,'restore_chat',lambda self:None):
            window=Window();window.show();window.timer.stop()
            def until(predicate,seconds=100):
                deadline=time.monotonic()+seconds
                while not predicate() and time.monotonic()<deadline: QTest.qWait(100)
                assert predicate(),window.editor.status.text()
            until(lambda:window.connected,20)
            assert window.client.url==expected==window.url.text()==window.editor.url
            assert window.editor.web.url().isEmpty()  # Hidden editor does not load another frontend.
            window.tabs.setCurrentIndex(1);until(lambda:window.editor.ready)
            assert window.editor.web.url().toString().rstrip('/')==expected
            assert expected in window.editor.connection_label.text()
            graph=build_workflow(ImageRequest(window.model.currentText(),'backend match test'))
            window.editor.sync_inputs(graph);until(lambda:not window.editor.pending)
            modified=deepcopy(graph)
            modified['5']['inputs']['positive']=['3',0];modified['5']['inputs']['negative']=['2',0]
            window.editor.sync_inputs(modified);until(lambda:not window.editor.pending)
            results=[];window.editor.snapshot(results.append);until(lambda:bool(results))
            assert results[0]['ok'],results
            actual=results[0]['value']['graph']
            sampler=next(node for node in actual.values() if node['class_type']=='KSampler')
            positive=actual[str(sampler['inputs']['positive'][0])]
            assert positive['inputs']['text']==modified['3']['inputs']['text']
            window.grab().save(str(DATA/'shared-backend-preview.png'))
            write_json(DATA/'shared-backend-acceptance.json',{'url':expected,'same_api_and_frontend':True,
                'hidden_frontend_lazy':True,'changed_links_reflected':True,'inference_submitted':False})
            window.editor.timer.stop()
            window.close();QTest.qWait(300)
    print('Shared backend, lazy editor and changed graph connections passed.')


if __name__=='__main__':main()
