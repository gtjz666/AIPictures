import unittest
from unittest.mock import patch
from aipictures.backend_connection import desktop_urls,shared_backend_url


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'ProcessId':10,'ParentProcessId':1,'Name':'Comfy Desktop.exe','CommandLine':''},
            {'ProcessId':20,'ParentProcessId':10,'Name':'python.exe','CommandLine':'python -s ComfyUI/main.py --port 8189'},
            {'ProcessId':21,'ParentProcessId':20,'Name':'python.exe','CommandLine':'python -s ComfyUI/main.py --port 8189'},
            {'ProcessId':30,'ParentProcessId':1,'Name':'python.exe','CommandLine':'python main.py --port 8188'}]

    def test_desktop_port_comes_from_actual_process_and_is_deduplicated(self):
        self.assertEqual(desktop_urls(self.rows),['http://127.0.0.1:8189'])
        self.rows[1]['CommandLine']='python main.py --port=8191'
        self.assertIn('http://127.0.0.1:8191',desktop_urls(self.rows))

    def test_local_default_reuses_open_desktop_but_custom_connection_is_preserved(self):
        with patch('aipictures.backend_connection.reachable',return_value=True):
            self.assertEqual(shared_backend_url('http://127.0.0.1:8188/',self.rows),'http://127.0.0.1:8189')
            self.assertEqual(shared_backend_url('http://127.0.0.1:9000',self.rows),'http://127.0.0.1:9000')

    def test_offline_desktop_does_not_change_the_connection(self):
        with patch('aipictures.backend_connection.reachable',return_value=False):
            self.assertEqual(shared_backend_url('http://localhost:8188',self.rows),'http://localhost:8188')


if __name__=='__main__': unittest.main()
