import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw
from aipictures.sprite_assets import export_pixel_assets
from sprite_pipeline import PipelineConfig, PipelineError, validate_output


class DesktopSpriteBridgeTests(unittest.TestCase):
    def test_native_frames_bypass_old_color_repairs_and_portable_zip_validates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); job=root/'job'; job.mkdir(); frames=[]
            for i in range(3):
                frame=job/f'frame_{i:03d}'; frame.mkdir()
                native=Image.new('RGBA',(24,32))
                ImageDraw.Draw(native).rectangle((6+i,4,17+i,27),fill='red')
                native.save(frame/'matte_native.png')
                Image.new('RGBA',(48,64),'blue').save(job/f'frame_{i:03d}.png')
                frames.append({'image':f'frame_{i:03d}.png','native_matte':f'frame_{i:03d}/matte_native.png'})
            manifest=job/'sequence.json'
            manifest.write_text(json.dumps({'status':'completed','frames':frames,'fps':8,'seed':42}),encoding='utf-8')
            before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in job.rglob('*.png')}
            anchor=root/'anchor.png'; Image.open(job/frames[0]['native_matte']).save(anchor)
            config=PipelineConfig(canvas_width=16,canvas_height=20,pixel_size=2,palette_size=4,anchor=str(anchor),seed=42)
            result=export_pixel_assets(manifest,root/'sprites.zip',config)
            self.assertTrue(result['report']['pass'])
            with zipfile.ZipFile(root/'sprites.zip') as archive:
                archive.extractall(root/'extracted')
                metadata=json.loads(archive.read('sprite_sheet.json'))
                self.assertEqual(metadata['frames'][0]['source']['path'],str((job/frames[0]['native_matte']).resolve()))
            anchor.unlink()  # Packaged anchor must remain usable after original moves.
            report=validate_output(root/'extracted')
            self.assertTrue(report['pass'])
            self.assertEqual(report['checks']['shared_palette']['colors'],[[255,0,0]])
            self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in job.rglob('*.png')})

    def test_legacy_cache_warns_and_original_target_is_protected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); job=root/'job'; job.mkdir()
            Image.new('RGBA',(8,8),'red').save(job/'one.png')
            manifest=job/'sequence.json'
            manifest.write_text(json.dumps({'status':'completed','frames':[{'image':'one.png'}],'fps':8,'seed':1}),encoding='utf-8')
            config=PipelineConfig(canvas_width=8,canvas_height=8,pixel_size=1,seed=1)
            result=export_pixel_assets(manifest,root/'out.zip',config)
            self.assertTrue(any('旧缓存' in warning for warning in result['report']['warnings']))
            with self.assertRaisesRegex(PipelineError,'覆盖'):
                export_pixel_assets(manifest,job/'one.png',config)


if __name__=='__main__': unittest.main()
