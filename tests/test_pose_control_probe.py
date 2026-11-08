"""Offline probe gates: busy/unknown queues must not permit a CUDA audit."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from tools.probe_sdpose_control import check_backends
from tools.probe_pose_control import source_samples


class PoseControlProbeTests(unittest.TestCase):
    def test_busy_and_malformed_queues_reject(self):
        for value in ({'queue_running': [[123]], 'queue_pending': []},
                      {'queue_running': [], 'queue_pending': [[456]]},
                      {'queue_running': []}, []):
            with self.subTest(value=value), patch('urllib.request.urlopen',
                    return_value=io.BytesIO(json.dumps(value).encode())):
                with self.assertRaises(ValueError):
                    check_backends(['http://127.0.0.1:8189'])

    def test_unreachable_and_unknown_are_distinct(self):
        with patch('urllib.request.urlopen', side_effect=URLError(ConnectionRefusedError())):
            self.assertEqual(check_backends(['http://127.0.0.1:8189'])[0]['status'], 'offline')
        with patch('urllib.request.urlopen', side_effect=URLError(TimeoutError())):
            with self.assertRaises(RuntimeError):
                check_backends(['http://127.0.0.1:8189'])

    def test_remote_urls_are_rejected_before_network(self):
        with patch('urllib.request.urlopen') as request:
            with self.assertRaises(ValueError):
                check_backends(['https://example.com'])
            request.assert_not_called()

    def test_variable_pts_select_real_frame_without_blending(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.gif'
            frames = [Image.new('RGB', (4, 4), color) for color in ('red', 'green', 'blue')]
            frames[0].save(path, save_all=True, append_images=frames[1:], duration=[100, 300, 200])
            samples, metadata = source_samples(path, [0, .099, .1, .399, .4, .599])
            self.assertEqual([r[2]['source_frame'] for r in samples], [0, 0, 1, 1, 2, 2])
            self.assertEqual(metadata['duration'], .6)
            self.assertEqual([r[1].getpixel((0, 0)) for r in samples],
                             [(255, 0, 0)]*2+[(0, 128, 0)]*2+[(0, 0, 255)]*2)
            with self.assertRaises(ValueError):
                source_samples(path, [.6])


if __name__ == '__main__':
    unittest.main()
