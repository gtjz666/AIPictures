import tempfile
import unittest
from pathlib import Path

from aipictures.result_cache import ResultCache
from aipictures.storage import write_json


class ResultCacheTests(unittest.TestCase):
    def test_selected_cleanup_preserves_exports_active_tasks_and_reference_data(self):
        with tempfile.TemporaryDirectory() as directory:
            data=Path(directory); cache=ResultCache(data)
            old=data/'jobs'/'old'; busy=data/'jobs'/'busy'; anim=data/'animations'/'cycle'
            for folder in (old,busy,anim):
                write_json(folder/'job.json',{'status':'completed'})
                (folder/'image.png').write_bytes(b'cache')
            reference=data/'characters'/'reference.png'; reference.parent.mkdir(); reference.write_bytes(b'reference')
            exported=data/'saved'/'chosen.png'; exported.parent.mkdir(); exported.write_bytes(b'saved')
            cache.record_save(exported,'image',old/'image.png')
            report=cache.clear([old,busy,old,anim],protected=[busy])
            self.assertEqual(set(report['deleted']),{str(old),str(anim)})
            self.assertEqual(report['skipped'],[str(busy)])
            self.assertFalse(report['errors']); self.assertTrue(busy.is_dir())
            self.assertEqual(exported.read_bytes(),b'saved'); self.assertEqual(reference.read_bytes(),b'reference')
            self.assertEqual(cache.saved_files()[0]['path'],str(exported))

    def test_refuses_cache_roots_outside_paths_and_unrecognized_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            data=Path(directory); cache=ResultCache(data)
            root=data/'jobs'; root.mkdir(); outside=data/'keep'; write_json(outside/'job.json',{})
            unknown=root/'manual-folder'; unknown.mkdir(); (unknown/'keep.txt').write_text('keep')
            report=cache.clear([root,outside,unknown])
            self.assertEqual(len(report['errors']),3)
            self.assertTrue((outside/'job.json').exists()); self.assertTrue((unknown/'keep.txt').exists())

    def test_explicit_exports_cannot_be_placed_in_disposable_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            data=Path(directory); cache=ResultCache(data)
            for path in (data/'jobs'/'a'/'keep.png',data/'animations'/'a'/'walk.zip'):
                with self.assertRaises(ValueError): cache.validate_export(path)
            target=data/'exports'/'walk.zip'
            self.assertEqual(cache.validate_export(target),target)


if __name__=='__main__': unittest.main()
