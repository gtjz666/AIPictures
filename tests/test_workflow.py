import unittest
from unittest.mock import MagicMock
from aipictures.workflow import ImageRequest, build_workflow
from aipictures.engine import ComfyClient


class WorkflowTests(unittest.TestCase):
    def test_lora_routing_and_vae(self):
        g = build_workflow(ImageRequest('model', 'cat', lora='style'))
        self.assertEqual(g['5']['inputs']['model'], ['8', 0])
        self.assertEqual(g['2']['inputs']['clip'], ['8', 1])
        self.assertEqual(g['6']['inputs']['vae'], ['1', 2])

    def test_invalid_dimensions(self):
        with self.assertRaises(ValueError): build_workflow(ImageRequest('m', 'cat', width=769))

    def test_remote_endpoint_rejected(self):
        with self.assertRaises(ValueError): ComfyClient('http://example.com:8188')

    def test_empty_success_response(self):
        client = ComfyClient()
        client.http = MagicMock()
        client.http.open.return_value.__enter__.return_value.read.return_value = b''
        self.assertEqual(client.request('/queue', {'delete': ['own-id']}), {})


if __name__ == '__main__': unittest.main()
