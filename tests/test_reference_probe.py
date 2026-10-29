import numpy as np
from PIL import Image
import pytest

from tools.qwen_reference_probe import build_workflow, instruction, prepare_input, composite_mask


def test_native_editor_keeps_chinese_and_fixed_seed_without_sdxl_lora():
    graph = build_workflow('original.png', '将外套改成红色', '不要改变背景', seed=123)
    assert '将外套改成红色' in graph['6']['inputs']['prompt']
    assert graph['7']['inputs']['prompt'] == '不要改变背景'
    assert graph['13']['inputs']['seed'] == 123
    assert graph['13']['inputs']['denoise'] == 1
    assert not any(n['class_type'] == 'LoraLoader' for n in graph.values())
    assert graph['10']['inputs']['pixels'] == ['5', 0]


def test_repair_uses_current_frame_and_unchanged_original_reference_not_history():
    graph = build_workflow('frame.png', '', task='repair', appearance_reference='anchor.png', size=(768, 1024))
    assert graph['4']['inputs']['image'] == 'frame.png'
    assert graph['appearance']['inputs']['image'] == 'anchor.png'
    assert graph['6']['inputs']['image2'] == ['appearance', 0]
    assert '第1张图的全身姿势' in graph['6']['inputs']['prompt']
    with pytest.raises(ValueError, match='原始参考图'):
        build_workflow('frame.png', '', task='repair')


def test_reference_preparation_preserves_opaque_rgb_without_cutting_background(tmp_path):
    original = tmp_path / 'source.png'; target = tmp_path / 'input.png'
    image = Image.new('RGB', (64, 64), (32, 90, 160)); image.save(original)
    prepare_input(original, target)
    assert np.array_equal(np.array(Image.open(target)), np.array(image))


def test_explicit_region_leaves_unselected_rgba_exact(tmp_path):
    original = tmp_path / 'source.png'; generated = tmp_path / 'generated.png'; mask = tmp_path / 'mask.png'
    source = Image.new('RGBA', (64, 64), (180, 90, 40, 128)); source.save(original)
    Image.new('RGBA', (64, 64), (60, 30, 200, 255)).save(generated)
    selected = Image.new('L', (64, 64)); selected.paste(255, (10, 20, 30, 40)); selected.save(mask)
    result = tmp_path / 'out.png'; report = composite_mask(original, generated, mask, result)
    pixels = np.array(Image.open(result)); before = np.array(source)
    outside = np.array(selected) == 0
    assert report['outside_mask_exact']
    assert np.array_equal(pixels[outside], before[outside])
    assert tuple(pixels[30, 20]) == (60, 30, 200, 255)


def test_style_change_is_explicit_instruction_and_blank_change_is_rejected():
    assert '水彩' in instruction('', 'layout', 'watercolor')
    with pytest.raises(ValueError, match='请描述'):
        instruction('')
