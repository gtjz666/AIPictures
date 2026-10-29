import json
from pathlib import Path
import threading
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image, ImageOps
import pytest

from aipictures.generation_reference import prepare_generation_reference, BACKGROUND
from aipictures.character_profile import rig_document
from aipictures.pose_animation import generate
from tools.compare_transparency_order import download_completed, review


def analysis_geometry(size=(768, 1024)):
    return {'canvas': list(size), 'direction': 'right', 'geometry': {
        'source_bbox': [0, 0, *size], 'offset': [0, 0],
        'subject_bbox': [0, 0, *size], 'scale': 1}}


def test_inference_reads_original_rgb_even_if_analysis_matte_erased_colors(tmp_path):
    source = tmp_path / 'source.png'
    Image.new('RGB', (64, 64), (180, 90, 40)).save(source)
    damaged = tmp_path / 'analysis.png'
    Image.new('RGBA', (64, 64), (255, 255, 255, 0)).save(damaged)
    analysis = dict(analysis_geometry((64, 64)), rgba=str(damaged), opaque=str(damaged))
    with patch('aipictures.background.foreground_rgba', side_effect=AssertionError('no matting for model input')):
        report = prepare_generation_reference(source, tmp_path / 'inference.png', analysis)
    assert not report['segmentation_applied']
    assert report['transparency_stage'] == 'after_animation_generation'
    with Image.open(report['path']) as image:
        assert image.mode == 'RGB'
        assert image.getpixel((32, 32)) == (180, 90, 40)


def test_existing_fractional_alpha_composited_once_and_source_untouched(tmp_path):
    source = tmp_path / 'source.png'
    rgba = Image.new('RGBA', (64, 64), (100, 30, 90, 128)); rgba.save(source)
    original_bytes = source.read_bytes()
    report = prepare_generation_reference(source, tmp_path / 'input.png', analysis_geometry((64, 64)))
    expected = Image.new('RGBA', (64, 64), (*BACKGROUND, 255)); expected.alpha_composite(rgba)
    assert np.array_equal(np.array(Image.open(report['path'])), np.array(expected.convert('RGB')))
    assert source.read_bytes() == original_bytes


def test_original_opaque_background_and_character_share_pose_transform(tmp_path):
    source = tmp_path / 'source.png'
    rgba = Image.new('RGBA', (80, 60), (90, 120, 40, 255))
    rgba.paste((180, 90, 40, 255), (20, 10, 40, 50)); rgba.save(source)
    analysis = {'canvas': [100, 100], 'direction': 'right', 'geometry': {
        'source_bbox': [20, 10, 40, 50], 'offset': [30, 20], 'subject_bbox': [30, 20, 50, 60], 'scale': 1}}
    prepare_generation_reference(source, tmp_path / 'input.png', analysis)
    with Image.open(tmp_path / 'input.png') as image:
        assert image.getpixel((35, 30)) == (180, 90, 40)
        assert image.getpixel((15, 15)) == (90, 120, 40)
        assert image.getpixel((99, 99)) == BACKGROUND
    analysis['direction'] = 'left'
    prepare_generation_reference(source, tmp_path / 'left.png', analysis)
    assert ImageOps.mirror(Image.open(tmp_path / 'input.png')).tobytes() == Image.open(tmp_path / 'left.png').tobytes()


def test_old_incomplete_analysis_fails_with_recovery_instruction(tmp_path):
    with pytest.raises(ValueError, match='重新分析'):
        prepare_generation_reference('source.png', tmp_path / 'out.png', {})


@pytest.mark.parametrize('text_only', [False, True])
def test_animation_does_not_matte_reference_before_inference(tmp_path, text_only):
    source = tmp_path / 'source.png'; Image.new('RGB', (768, 1024), (180, 90, 40)).save(source)
    rig = tmp_path / 'rig.json'; rig.write_text(json.dumps(rig_document()), encoding='utf-8')
    analysis = dict(analysis_geometry(), rig=str(rig))
    client = Mock()
    client.discover.return_value = {'object_info': {}}
    client.upload_image.side_effect = lambda p, **kw: Path(p).name
    raw = {'images': [str(source)] * 17, 'prompt_id': 'test-prompt'}
    client.generate.side_effect = [{'images': [str(source)], 'prompt_id': 'character'}, raw] if text_only else [raw]
    output = tmp_path / 'animation'; output.mkdir()
    with patch('aipictures.pose_animation.prepare_motion_reference', return_value=analysis), \
         patch('aipictures.pose_animation.release_idle_models', return_value={}), \
         patch('aipictures.pose_animation.bind_model_names'), \
         patch('aipictures.background.process_result', side_effect=AssertionError('must matte after animation only')):
        generate(client, output, 'a yellow cartoon dinosaur, white belly, side view', '', 42, 8, 8, Mock(), threading.Event(),
                 reference=None if text_only else source, checkpoint='test', raw_only=True)
    manifest = json.loads((output / 'sequence.json').read_text('utf-8'))
    assert manifest['generation_reference']['segmentation_applied'] is False
    graph = json.loads((output / 'video/workflow.json').read_text('utf-8'))
    assert graph['7']['inputs']['image'] == 'generation-reference.png'
    with Image.open(output / 'generation-reference.png') as image:
        assert image.getpixel((384, 500)) == (180, 90, 40)


def test_completed_experiment_can_recover_to_new_directory_without_resubmitting(tmp_path):
    client = Mock()
    history = {'status': {'status_str': 'success'}, 'outputs': {'save': {'images': [
        {'filename': 'generated.png', 'type': 'output'}]}}}
    client.request.side_effect = [{'mine': history}, b'original-image-bytes']
    result = download_completed(client, 'mine', tmp_path / 'not-created' / 'video')
    assert Path(result['images'][0]).read_bytes() == b'original-image-bytes'
    assert client.request.call_count == 2
    assert client.request.call_args_list[0].args == ('/history/mine',)
    assert client.request.call_args_list[1].args[0].startswith('/view?')


def test_incomplete_experiment_does_not_automatically_submit_new_job(tmp_path):
    client = Mock(); client.request.return_value = {}
    with pytest.raises(ValueError, match='不会自动重新生成'):
        download_completed(client, 'mine', tmp_path / 'video')
    client.request.assert_called_once_with('/history/mine', timeout=120)


def test_comparison_reports_raw_difference_and_independent_rgb_preservation(tmp_path):
    sequence = tmp_path / 'sequence'; (sequence / 'video').mkdir(parents=True)
    out = tmp_path / 'comparison'; out.mkdir()
    before_paths = []; after_paths = []
    for i in range(3):
        old = tmp_path / f'old_{i}.png'; new = tmp_path / f'new_{i}.png'
        Image.new('RGB', (16, 24), (180, 90, 40)).save(old)
        Image.new('RGB', (16, 24), (181, 91, 41)).save(new)
        before_paths.append(str(old)); after_paths.append(str(new))
    (sequence / 'sequence.json').write_text(json.dumps({'frame_count': 2}), encoding='utf-8')
    (sequence / 'video/result.json').write_text(json.dumps({'images': before_paths, 'prompt_id': 'before'}), encoding='utf-8')
    with patch('tools.compare_transparency_order.foreground_rgba', side_effect=lambda image,*a,**kw:image.copy()), \
         patch('tools.compare_transparency_order.release_session'):
        review(sequence, out, {}, {'images': after_paths, 'prompt_id': 'after'})
    report = json.loads((out / 'experiment.json').read_text('utf-8'))
    assert report['raw_frame_count_per_group'] == 3
    assert all(row['mean_absolute_channel_change'] == 1 for row in report['raw_frame_differences'])
    assert len(report['frames']) == 4
    assert all(row['rgb_preserved_by_matting'] for row in report['frames'])
    assert (out / 'comparison.png').is_file()
