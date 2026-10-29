"""Synthetic asset acceptance; no model, network, Qt or GPU required."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from sprite_pipeline import PipelineConfig, PipelineError, load_config, run_pipeline, run_stage, validate_output
from sprite_pipeline.config import write_document
from sprite_pipeline.pixels import estimate_pixel_size, normalize_image, snap_image
from sprite_pipeline.validation import audit_processing_code


class SpritePipelineTests(unittest.TestCase):
    def test_blurred_blocks_and_gray_edge_collapse_to_true_pixels(self):
        image = Image.new('RGBA', (32, 24), 'black')
        ImageDraw.Draw(image).rectangle((16, 0, 31, 23), fill='white')
        image = image.filter(ImageFilter.GaussianBlur(.6))
        result, report = snap_image(image, PipelineConfig(pixel_size=4, palette_size=3))
        self.assertEqual(result.size, (8, 6))
        colors = np.unique(np.asarray(result)[:, :, :3].reshape(-1, 3), axis=0)
        self.assertEqual(colors.tolist(), [[0, 0, 0], [255, 255, 255]])
        enlarged = result.resize((32, 24), Image.Resampling.NEAREST)
        for y in range(0, 24, 4):
            for x in range(0, 32, 4):
                self.assertEqual(len(enlarged.crop((x, y, x+4, y+4)).getcolors()), 1)

    def test_rare_axis_transition_takes_existing_neighbor_color(self):
        image = Image.new('RGBA', (32, 24), 'black')
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 0, 31, 23), fill='white')
        draw.line((15, 0, 15, 23), fill=(128, 128, 128, 255))
        result, report = snap_image(image, PipelineConfig(pixel_size=1, palette_size=3))
        self.assertGreater(report['merged_transition_pixels'], 0)
        self.assertEqual(len(result.getcolors()), 2)

    def test_auto_grid_detects_period_and_falls_back_on_uninformative_image(self):
        cells = np.indices((12, 12)).sum(axis=0) % 2 * 255
        image = Image.fromarray(cells.astype('uint8')).convert('RGBA').resize((48, 48), Image.Resampling.NEAREST)
        size, confidence, _ = estimate_pixel_size(image)
        self.assertEqual(size, 4)
        self.assertGreater(confidence, .45)
        size, confidence, warnings = estimate_pixel_size(Image.new('RGBA', (32, 32), 'red'))
        self.assertEqual((size, confidence), (1, 0.0))
        self.assertTrue(warnings)

    def test_alpha_threshold_is_binary_and_transparent_rgb_does_not_enter_palette(self):
        image = Image.new('RGBA', (8, 4), (0, 255, 0, 0))
        image.putpixel((2, 2), (255, 0, 0, 180))
        image.putpixel((3, 2), (255, 255, 255, 100))
        result, report = snap_image(image, PipelineConfig(pixel_size=1, palette_size=2))
        self.assertEqual(report['fractional_alpha_pixels'], 2)
        self.assertEqual(result.getpixel((2, 2)), (255, 0, 0, 255))
        self.assertEqual(result.getpixel((3, 2)), (0, 0, 0, 0))
        self.assertTrue(set(np.asarray(result)[:, :, 3].ravel()) <= {0, 255})

    def test_three_offset_frames_normalize_to_same_anchor_without_scaling(self):
        results = []
        for dx, dy in ((3, 5), (20, 14), (34, 32)):
            image = Image.new('RGBA', (64, 64))
            ImageDraw.Draw(image).rectangle((dx, dy, dx+6, dy+11), fill=(200, 20, 30, 255))
            result, record = normalize_image(image, PipelineConfig(canvas_width=16, canvas_height=20))
            self.assertEqual(record['scale'], 1)
            self.assertEqual(record['anchor'][1], 20)
            self.assertLessEqual(abs(record['anchor'][0]-8), .5)
            results.append(np.asarray(result))
        self.assertTrue(all(np.array_equal(results[0], result) for result in results))

    def test_bbox_center_and_manual_offsets_preserve_motion(self):
        image = Image.new('RGBA', (24, 24))
        ImageDraw.Draw(image).rectangle((2, 3, 5, 8), fill='red')
        result, record = normalize_image(image, PipelineConfig(canvas_width=20, canvas_height=20, anchor_mode='bbox-center'))
        self.assertEqual(record['anchor'], [10, 10])
        result, record = normalize_image(image, PipelineConfig(canvas_width=32, canvas_height=32, anchor_mode='manual', manual_offset=(5, 2)))
        self.assertEqual(result.getchannel('A').getbbox(), (7, 5, 11, 11))
        self.assertEqual(record['translation'], [5, 2])

    def test_oversize_is_error_until_explicit_nearest_fit(self):
        image = Image.new('RGBA', (32, 32), (40, 80, 120, 255))
        config = PipelineConfig(canvas_width=16, canvas_height=16)
        with self.assertRaisesRegex(PipelineError, 'allow-scale'):
            normalize_image(image, config)
        result, report = normalize_image(image, replace(config, allow_scale=True))
        self.assertEqual(result.getpixel((0, 0)), (40, 80, 120, 255))
        self.assertEqual(report['scale'], .5)
        with self.assertRaisesRegex(PipelineError, '裁掉'):
            normalize_image(image, replace(config, canvas_width=40, canvas_height=40, anchor_mode='manual', manual_offset=(-1, 0)))

    @staticmethod
    def make_frames(root):
        source = root/'input frames'; source.mkdir()
        anchor = root/'anchor.png'
        for number, shift in ((10, 6), (2, 3), (1, 0)):
            image = Image.new('RGBA', (16, 16))
            draw = ImageDraw.Draw(image)
            draw.rectangle((3, 2, 8, 7), fill=(180+shift, 40+shift, 60+shift, 255))
            draw.rectangle((3, 8, 8, 13), fill=(30+shift, 70+shift, 150+shift, 255))
            image.save(source/f'frame_{number}.png')
            if number == 1:
                image.save(anchor)
        return source, anchor

    def test_shared_anchor_palette_controls_three_frames_without_dithering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, anchor = self.make_frames(root)
            config = PipelineConfig(canvas_width=16, canvas_height=16, pixel_size=1, palette_size=2, anchor=str(anchor), seed=23)
            out = root/'out'; run_stage('palette', source, out, config)
            palette = json.loads((out/'palette.json').read_text('utf-8'))['colors']
            for path in (out/'frames').glob('*.png'):
                with Image.open(path) as image:
                    array = np.asarray(image); colors = np.unique(array[:, :, :3][array[:, :, 3] > 0], axis=0)
                self.assertEqual(sorted(colors.tolist()), sorted(palette))
            state = json.loads((out/'pipeline-state.json').read_text('utf-8'))
            self.assertEqual(state['stages']['palette']['frames'][0]['mean_rgb_distance'], 0)
            self.assertGreater(state['stages']['palette']['frames'][-1]['mean_rgb_distance'], 0)

    def test_run_sheet_roundtrip_natural_order_padding_and_source_immutability(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, anchor = self.make_frames(root)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.png')}
            config = PipelineConfig(canvas_width=16, canvas_height=20, pixel_size=1, palette_size=2,
                                    anchor=str(anchor), padding=2, columns=2, seed=7654)
            report = run_pipeline(source, root/'out', config)
            self.assertTrue(report['pass'], report)
            self.assertTrue(report['checks']['anchor_palette_distance']['within_threshold'])
            self.assertEqual(report['checks']['anchor_drift']['max_extent_pixels'], 0)
            meta = json.loads((root/'out/sprite_sheet.json').read_text('utf-8'))
            self.assertEqual([e['name'] for e in meta['frames']], ['frame_1.png', 'frame_2.png', 'frame_10.png'])
            self.assertEqual((meta['columns'], meta['rows']), (2, 2))
            self.assertEqual(meta['generation']['seed'], 7654)
            with Image.open(root/'out/sprite_sheet.png') as sheet:
                self.assertEqual(sheet.size, (38, 46))
                self.assertEqual(sheet.getpixel((0, 0)), (0, 0, 0, 0))
                for entry in meta['frames']:
                    r = entry['rect']; tile = sheet.crop((r['x'], r['y'], r['x']+r['w'], r['y']+r['h']))
                    with Image.open(root/'out'/entry['file']) as frame:
                        self.assertTrue(np.array_equal(np.asarray(tile), np.asarray(frame)))
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.png')})

    def test_sequence_palette_without_anchor_and_empty_frame(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, _ = self.make_frames(root)
            Image.new('RGBA', (16, 16)).save(source/'frame_3.png')
            report = run_pipeline(source, root/'out', PipelineConfig(canvas_width=16, canvas_height=16, pixel_size=1, palette_size=3))
            self.assertTrue(report['pass'])
            self.assertTrue(any('空白' in warning for warning in report['warnings']))
            self.assertTrue(any('没有锚点图' in warning for warning in report['warnings']))
            self.assertLessEqual(max(f['unique_colors'] for f in report['frames']), 3)

    def test_auto_grid_is_shared_for_entire_sequence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root/'in'; source.mkdir()
            array = np.indices((12, 12)).sum(axis=0) % 2 * 255
            Image.fromarray(array.astype('uint8')).convert('RGBA').resize((48, 48), Image.Resampling.NEAREST).save(source/'frame_1.png')
            Image.new('RGBA', (48, 48), 'red').save(source/'frame_2.png')
            run_stage('snap', source, root/'out', PipelineConfig())
            state = json.loads((root/'out/pipeline-state.json').read_text('utf-8'))
            self.assertEqual([r['pixel_size'] for r in state['stages']['snap']['frames']], [4, 4])

    def test_validation_catches_sheet_and_alpha_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, anchor = self.make_frames(root)
            config = PipelineConfig(canvas_width=16, canvas_height=16, pixel_size=1, palette_size=2, anchor=str(anchor))
            run_pipeline(source, root/'out', config)
            path = root/'out/frames/frame_1.png'
            with Image.open(path) as frame:
                image = frame.convert('RGBA')
            image.putpixel((0, 0), (0, 255, 0, 123)); image.save(path)
            report = validate_output(root/'out')
            self.assertFalse(report['pass'])
            self.assertFalse(report['checks']['sheet_roundtrip']['pass'])
            self.assertFalse(report['checks']['binary_alpha']['pass'])
            self.assertFalse(report['checks']['shared_palette']['pass'])

    def test_validation_rejects_a_different_anchor_palette(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, anchor = self.make_frames(root)
            config = PipelineConfig(canvas_width=16, canvas_height=16, pixel_size=1, palette_size=2, anchor=str(anchor))
            run_pipeline(source, root/'out', config)
            Image.new('RGBA', (16, 16), 'lime').save(anchor)
            report = validate_output(root/'out')
            self.assertFalse(report['pass'])
            self.assertFalse(report['checks']['anchor_palette_distance']['pass'])

    def test_drift_warning_for_manual_motion_not_a_false_structural_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root/'in'; source.mkdir()
            for i in range(3):
                image = Image.new('RGBA', (16, 16))
                ImageDraw.Draw(image).rectangle((2+i*3, 2, 4+i*3, 7), fill='red')
                image.save(source/f'frame_{i}.png')
            report = run_pipeline(source, root/'out', PipelineConfig(canvas_width=16, canvas_height=16, pixel_size=1, anchor_mode='manual', drift_threshold=1))
            self.assertTrue(report['pass'])
            self.assertFalse(report['checks']['anchor_drift']['within_threshold'])
            self.assertTrue(any('锚点漂移' in warning for warning in report['warnings']))

    def test_determinism_repeated_run_matches_every_frame_and_sheet(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, _ = self.make_frames(root)
            config = PipelineConfig(canvas_width=16, canvas_height=16, pixel_size=1, palette_size=3, seed=42)
            run_pipeline(source, root/'a', config); run_pipeline(source, root/'b', config)
            for path in (root/'a/frames').glob('*.png'):
                self.assertEqual(path.read_bytes(), (root/'b/frames'/path.name).read_bytes())
            self.assertEqual((root/'a/sprite_sheet.png').read_bytes(), (root/'b/sprite_sheet.png').read_bytes())

    def test_bad_config_and_safe_output_directory(self):
        for changes in ({'palette_size':257}, {'seed':-1}, {'seed':True}, {'fps':float('nan')}, {'pixel_size':0}, {'manual_offset':[1]}, {'allow_scale':'false'}):
            with self.subTest(changes=changes), self.assertRaises(PipelineError):
                replace(PipelineConfig(), **changes).validate()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, _ = self.make_frames(root)
            with self.assertRaises(PipelineError):
                run_stage('snap', source, source, PipelineConfig(pixel_size=1))
            folder = root/'out/frames'; folder.mkdir(parents=True)
            Image.new('RGBA', (8, 8)).save(folder/'user-file.png')
            with self.assertRaisesRegex(PipelineError, '防止覆盖'):
                run_stage('snap', source, root/'out', PipelineConfig(pixel_size=1))

    def test_grid_overflow_errors_without_replacing_processed_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, _ = self.make_frames(root)
            out = root/'out'; config = PipelineConfig(canvas_width=16, canvas_height=16, pixel_size=1, columns=1, rows=1)
            with self.assertRaisesRegex(PipelineError, '容不下'):
                run_stage('assemble', source, out, config)
            self.assertFalse((out/'frames').exists())

    def test_failed_normalization_writes_failed_report_without_rescaling(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, _ = self.make_frames(root)
            with self.assertRaisesRegex(PipelineError, 'allow-scale'):
                run_pipeline(source, root/'out', PipelineConfig(canvas_width=4, canvas_height=4, pixel_size=1))
            report = json.loads((root/'out/report.json').read_text('utf-8'))
            self.assertFalse(report['pass'])
            self.assertEqual(report['status'], 'processing_failed')
            self.assertEqual(report['stage'], 'normalize')
            with Image.open(root/'out/frames/frame_1.png') as image:
                self.assertEqual(image.size, (16, 16))

    def test_code_audit_passes_and_detects_banned_calls_dependencies(self):
        self.assertTrue(audit_processing_code()['pass'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); package = root/'sprite_pipeline'; package.mkdir()
            (root/'requirements.txt').write_text('dlss==1\n')
            (package/'bad.py').write_text('def bad():\n    return fxaa()\n')
            report = audit_processing_code(package)
            self.assertFalse(report['pass']); self.assertEqual(len(report['findings']), 2)

    def test_yaml_relative_anchor_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); _, anchor = self.make_frames(root)
            write_document(root/'pipeline.yaml', {'anchor':'anchor.png', 'seed':42})
            self.assertEqual(load_config(root/'pipeline.yaml').anchor, str(anchor.resolve()))
            write_document(root/'bad.json', {'mystery': 1})
            with self.assertRaisesRegex(PipelineError, '未知'):
                load_config(root/'bad.json')

    def test_all_six_cli_commands_and_nonzero_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, anchor = self.make_frames(root)
            output = root/'output with spaces'; config = root/'pipeline.yaml'
            def cli(*args):
                return subprocess.run([sys.executable, '-m', 'sprite_pipeline', *map(str, args)], capture_output=True, text=True, encoding='utf-8', errors='replace')
            result = cli('config', '--out', config, '--seed', 42, '--anchor', anchor, '--canvas-width', 16, '--canvas-height', 16, '--pixel-size', 1, '--palette-size', 2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(cli('config', '--check', config).returncode, 0)
            for stage in ('snap', 'normalize', 'palette', 'assemble'):
                result = cli(stage, source if stage == 'snap' else output/'frames', '--out', output, '--config', config)
                self.assertEqual(result.returncode, 0, (stage, result.stderr))
            result = cli('validate', '--out', output)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = cli('snap', source, '--out', root/'bad', '--pixel-size', 'zero')
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
