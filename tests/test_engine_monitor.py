import itertools
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError
import websocket

from aipictures.engine import ComfyClient, EngineUnavailable, Cancelled


class MonitorRetryTests(unittest.TestCase):
    def test_owned_backend_interruption_is_cancelled_not_a_generation_error(self):
        client=ComfyClient(); client.request=Mock(return_value={'prompt_id':'owned'})
        ws=Mock(); ws.recv.return_value=json.dumps({'type':'execution_interrupted','data':{'prompt_id':'owned'}})
        with tempfile.TemporaryDirectory() as directory,patch('aipictures.engine.websocket.create_connection',return_value=ws):
            with self.assertRaises(Cancelled):
                client.generate({},Path(directory),lambda *args:None,threading.Event())
        ws.close.assert_called_once()

    def test_refused_http_is_actionable_and_not_an_endless_busy_wait(self):
        client=ComfyClient(); client.http=Mock()
        client.http.open.side_effect=URLError(ConnectionRefusedError(10061,'refused'))
        with self.assertRaisesRegex(EngineUnavailable,'启动本地引擎'):
            client.request('/system_stats')
        with self.assertRaises(EngineUnavailable): client.upload_image(Path(__file__))

    def test_engine_loss_after_submission_never_resubmits(self):
        client=ComfyClient(); calls=[]
        def request(path,body=None,raw=False):
            calls.append(path)
            if path=='/prompt': return {'prompt_id':'owned'}
            raise EngineUnavailable(client.url)
        client.request=request
        ws=Mock(); ws.recv.side_effect=websocket.WebSocketConnectionClosedException()
        with tempfile.TemporaryDirectory() as directory,patch('aipictures.engine.websocket.create_connection',return_value=ws):
            with self.assertRaises(EngineUnavailable):
                client.generate({},Path(directory),lambda *args:None,threading.Event())
        self.assertEqual(calls.count('/prompt'),1)
        ws.close.assert_called_once()

    def test_websocket_loss_with_live_http_still_downloads_same_job(self):
        client=ComfyClient(); calls=[]
        def request(path,body=None,raw=False):
            calls.append(path)
            if path=='/prompt': return {'prompt_id':'owned'}
            if path.startswith('/history/'):
                return {'owned':{'outputs':{'7':{'images':[{'filename':'result.png'}]}}}}
            if path.startswith('/view?'): return b'image'
            raise AssertionError(path)
        client.request=request; ws=Mock()
        ws.recv.side_effect=websocket.WebSocketConnectionClosedException()
        with tempfile.TemporaryDirectory() as directory,patch('aipictures.engine.websocket.create_connection',return_value=ws):
            result=client.generate({},Path(directory),lambda *args:None,threading.Event())
            self.assertEqual(Path(result['images'][0]).read_bytes(),b'image')
        self.assertEqual(calls.count('/prompt'),1)

    def test_history_timeout_does_not_resubmit_prompt(self):
        client = ComfyClient()
        calls = []; histories = []
        def request(path, body=None, raw=False):
            calls.append(path)
            if path == '/prompt': return {'prompt_id':'owned-prompt'}
            if path.startswith('/history/'):
                histories.append(path)
                if len(histories) == 1: raise TimeoutError('busy during decode')
                return {'owned-prompt': {'status': {'status_str':'success'},
                    'outputs': {'7': {'images': [{'filename':'result.png','type':'output'}]},
                                '15': {'latents': [{'filename':'samples.latent','type':'output'}]}}}}
            if path.startswith('/view?'): return b'latent tensor bytes' if '.latent' in path else b'local image bytes'
            raise AssertionError(path)
        client.request = request
        ws = Mock(); ws.recv.return_value = json.dumps({'type':'status','data':{}})
        events = []
        with tempfile.TemporaryDirectory() as directory, patch('aipictures.engine.websocket.create_connection',return_value=ws), patch('aipictures.engine.time.monotonic',side_effect=itertools.count()):
            result = client.generate({},Path(directory),lambda kind,data: events.append(kind),threading.Event())
            self.assertEqual(Path(result['images'][0]).read_bytes(),b'local image bytes')
            self.assertEqual(Path(result['latents'][0]).read_bytes(),b'latent tensor bytes')
        self.assertEqual(calls.count('/prompt'),1)
        self.assertIn('monitor_waiting',events)
        ws.close.assert_called_once()


if __name__ == '__main__': unittest.main()
