import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from aipictures.engine import Cancelled
from aipictures.engine_service import release_idle_models
from aipictures.pose_animation import generate


class CleanupTests(unittest.TestCase):
    def test_cancelled_preparation_records_result_and_yields_its_idle_model_cache(self):
        with tempfile.TemporaryDirectory() as temp,patch('aipictures.pose_animation.release_idle_models',return_value={'released':True}) as release,patch(
            'aipictures.pose_animation.prepare_motion_reference',side_effect=Cancelled('test cancellation')):
            client=Mock();folder=Path(temp)
            with self.assertRaises(Cancelled):
                generate(client,folder,'walk','',1,8,8,Mock(),threading.Event(),reference='reference.png')
            manifest=json.loads((folder/'sequence.json').read_text('utf-8'))
            self.assertEqual(manifest['status'],'cancelled')
            self.assertTrue(manifest['final_cache_release']['released'])
            self.assertEqual(release.call_count,2)

    def test_cache_release_never_unloads_while_another_job_is_present(self):
        for key in ('queue_running','queue_pending'):
            client=Mock();client.request.return_value={key:[['another-job']]}
            self.assertEqual(release_idle_models(client)['reason'],'engine_busy')
            client.request.assert_called_once_with('/queue')


if __name__=='__main__':unittest.main()
