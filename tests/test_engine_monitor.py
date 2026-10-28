import itertools
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aipictures.engine import ComfyClient


class MonitorRetryTests(unittest.TestCase):
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
