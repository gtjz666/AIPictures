import subprocess
import unittest
from unittest.mock import Mock,patch

from aipictures.engine_service import start_local_engine


class EngineStartTests(unittest.TestCase):
    def setUp(self):
        selector=patch('aipictures.backend_connection.shared_backend_url',side_effect=lambda url:url)
        selector.start(); self.addCleanup(selector.stop)

    def test_running_engine_is_never_started_again(self):
        with patch('aipictures.engine_service.ComfyClient') as client,patch('aipictures.engine_service.subprocess.run') as run:
            client.return_value.url='http://127.0.0.1:8188'
            self.assertEqual(start_local_engine('http://127.0.0.1:8188',Mock()),'http://127.0.0.1:8188')
            run.assert_not_called()
            client.return_value.request.assert_called_once_with('/system_stats')

    def test_wrong_port_does_not_launch_unrelated_server(self):
        with patch('aipictures.engine_service.ComfyClient') as client,patch('aipictures.engine_service.subprocess.run') as run:
            client.return_value.request.side_effect=ConnectionRefusedError()
            with self.assertRaisesRegex(ValueError,'8188'):
                start_local_engine('http://127.0.0.1:8199',Mock())
            run.assert_not_called()

    def test_closed_engine_waits_for_readiness_and_uses_hidden_existing_script(self):
        with patch('aipictures.engine_service.ComfyClient') as client,patch('aipictures.engine_service.subprocess.run') as run:
            client.return_value.request.side_effect=[ConnectionRefusedError(),{}]
            client.return_value.url='http://127.0.0.1:8188'
            run.return_value=Mock(returncode=0)
            self.assertTrue(start_local_engine('http://127.0.0.1:8188',Mock()))
            args=run.call_args
            self.assertTrue(args.args[0][-1].endswith('start-comfy.ps1'))
            self.assertEqual(args.kwargs['creationflags'],subprocess.CREATE_NO_WINDOW)
            self.assertNotIn('capture_output',args.kwargs)
            self.assertNotEqual(args.kwargs['stdout'],subprocess.PIPE)
            self.assertEqual(client.return_value.request.call_count,2)


if __name__=='__main__': unittest.main()
