"""Experimental native Qwen editing probe; deliberately not a default animation pass.

The first real repair restored missing color but moved the character's framing.
Keep this independently runnable for research; it does not modify the GUI route.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

MODEL = 'qwen_image_edit_2511_fp8mixed.safetensors'
ENCODER = 'qwen_2.5_vl_7b_fp8_scaled.safetensors'
VAE = 'qwen_image_vae.safetensors'
STYLE_PRESETS = {
    'custom': '',
    'anime': '日系动漫赛璐璐画风，清晰线稿，完整均匀配色',
    'photo': '写实摄影风格，自然材质与光照',
    'watercolor': '水彩插画风格，保留清晰的主体结构',
    'cartoon3d': '精致的3D卡通风格，清晰材质与柔和光照',
    'pixel': '游戏像素插画风格，清晰色块和轮廓',
}


def instruction(prompt: str, task: str = 'edit', style: str = 'custom') -> str:
    if task not in ('edit', 'layout', 'repair') or style not in STYLE_PRESETS:
        raise ValueError('未知参考图编辑方式或画风。')
    text = prompt.strip()
    if task == 'repair':
        return ('第1张图是需要修复的动画帧，第2张图是同一个角色的身份、服装、颜色和细节基准。'
                '精确保留第1张图的全身姿势、四肢位置、朝向、构图、主体大小和镜头；不要改成第2张图的站姿。'
                '根据第2张图修复第1张图丢失的肤色、衣服与袜子颜色、头发、鞋子、线稿和纹理细节。'
                '恢复被错误画成白色的皮肤、衣服和袜子区域。保持第2张图原本的色块、渐变、配饰和绘画风格。'
                '不要添加新物件、额外肢体或重复鞋子，不改变光照与曝光，背景保持简单。只输出修复后的第1张图。')
    if not text and not STYLE_PRESETS[style]:
        raise ValueError('请描述要修改的内容或画风；例如“将外套改成红色，其余保持不变”。')
    if task == 'layout':
        prefix = ('保持参考图的画幅比例、构图排版、主体数量、相对位置、大小、姿态、朝向和透视。'
                  '按照以下要求修改画风或材质，不重新排列画面，不添加无关物件：')
    else:
        prefix = ('以参考图为基准，执行以下修改。仅改变明确要求改变的部分；'
                  '未要求修改的角色身份、五官、服装细节、背景与构图尽量保持一致：')
    return prefix + text + ('。画风：' + STYLE_PRESETS[style] if STYLE_PRESETS[style] else '')


def build_workflow(reference: str, prompt: str, negative: str = '', *, seed: int = 42,
                   steps: int = 40, cfg: float = 4., task: str = 'edit', style: str = 'custom',
                   appearance_reference: str | None = None, size: tuple[int, int] | None = None) -> dict[str, Any]:
    if not reference:
        raise ValueError('参考编辑需要主动添加参考图；纯文字生成请使用通用创作。')
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError('参考编辑需要有效的固定 seed。')
    if not 1 <= steps <= 150 or not 0 <= cfg <= 30:
        raise ValueError('参考编辑步数或 CFG 超出范围。')
    if task == 'repair' and not appearance_reference:
        raise ValueError('动画细节修复需要同一角色的原始参考图。')
    graph = {
        '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': MODEL, 'weight_dtype': 'default'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': ENCODER, 'type': 'qwen_image', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': VAE}},
        '4': {'class_type': 'LoadImage', 'inputs': {'image': reference}, '_meta': {'title': '本次用户参考图'}},
        '5': {'class_type': 'FluxKontextImageScale', 'inputs': {'image': ['4', 0]}},
        '6': {'class_type': 'TextEncodeQwenImageEditPlus', 'inputs': {'clip': ['2', 0], 'vae': ['3', 0], 'image1': ['5', 0], 'prompt': instruction(prompt, task, style)}},
        '7': {'class_type': 'TextEncodeQwenImageEditPlus', 'inputs': {'clip': ['2', 0], 'vae': ['3', 0], 'image1': ['5', 0], 'prompt': negative}},
        '8': {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': ['1', 0], 'shift': 3.1}},
        '9': {'class_type': 'CFGNorm', 'inputs': {'model': ['8', 0], 'strength': 1.}},
        '10': {'class_type': 'VAEEncode', 'inputs': {'pixels': ['5', 0], 'vae': ['3', 0]}},
        '11': {'class_type': 'FluxKontextMultiReferenceLatentMethod', 'inputs': {'conditioning': ['6', 0], 'reference_latents_method': 'index_timestep_zero'}},
        '12': {'class_type': 'FluxKontextMultiReferenceLatentMethod', 'inputs': {'conditioning': ['7', 0], 'reference_latents_method': 'index_timestep_zero'}},
        '13': {'class_type': 'KSampler', 'inputs': {'model': ['9', 0], 'positive': ['11', 0], 'negative': ['12', 0], 'latent_image': ['10', 0],
              'seed': seed, 'steps': steps, 'cfg': cfg, 'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1.}},
        '14': {'class_type': 'VAEDecode', 'inputs': {'samples': ['13', 0], 'vae': ['3', 0]}},
        '15': {'class_type': 'SaveImage', 'inputs': {'images': ['14', 0], 'filename_prefix': 'AIPictures/reference_edit'}},
    }
    if size:
        width, height = size
        if width % 16 or height % 16 or min(width, height) < 64:
            raise ValueError('编辑画布必须为至少 64 且为 16 的倍数。')
        graph['5'] = {'class_type': 'ImageScale', 'inputs': {'image': ['4', 0], 'upscale_method': 'lanczos',
                                                          'width': width, 'height': height, 'crop': 'disabled'}}
    if appearance_reference:
        graph['appearance'] = {'class_type': 'LoadImage', 'inputs': {'image': appearance_reference}, '_meta': {'title': '固定角色外观基准'}}
        for key in ('6', '7'):
            graph[key]['inputs']['image2'] = ['appearance', 0]
    return graph


def check_models(info: dict[str, Any]) -> str | None:
    """A disabled-choice reason, or None when the existing backend supports editing."""
    graph = build_workflow('reference', '测试')
    missing = sorted({n['class_type'] for n in graph.values()} - set(info))
    if missing:
        return '缺少参考编辑节点：' + '、'.join(missing)
    for kind, field, name in (('UNETLoader', 'unet_name', MODEL), ('CLIPLoader', 'clip_name', ENCODER), ('VAELoader', 'vae_name', VAE)):
        spec = info[kind]['input']['required'][field]
        choices = spec[0] if isinstance(spec[0], list) else spec[1].get('options', [])
        if name not in choices:
            return '缺少参考编辑模型：' + name
    return None


def prepare_input(source: str | Path, target: str | Path) -> str:
    """Composite straight alpha onto neutral grey; black transparent RGB is not content."""
    with Image.open(source) as image:
        rgba = ImageOps.exif_transpose(image).convert('RGBA')
    background = Image.new('RGBA', rgba.size, '#eeeeee')
    background.alpha_composite(rgba)
    background.convert('RGB').save(target)
    return str(target)


def composite_mask(source: str | Path, generated: str | Path, mask: str | Path, target: str | Path) -> dict[str, Any]:
    """An explicit local edit guarantees exact RGBA outside the user-painted mask."""
    with Image.open(source) as image:
        original = ImageOps.exif_transpose(image).convert('RGBA')
    with Image.open(mask) as image:
        selected = image.convert('L')
    if selected.size != original.size:
        raise ValueError('修改区域与当前参考图尺寸不一致，请重新绘制修改区域。')
    selected = selected.point(lambda value: 255 if value >= 128 else 0)
    if not selected.getbbox():
        raise ValueError('修改区域为空，请涂选要改变的部分或清除区域限制。')
    with Image.open(generated) as image:
        patch = image.convert('RGBA')
        if patch.size != original.size:
            patch = patch.resize(original.size, Image.Resampling.LANCZOS)
    output = Image.composite(patch, original, selected)
    output.save(target)
    return {'method': 'explicit_binary_region_composite', 'outside_mask_exact': True,
            'mask_bbox': selected.getbbox(), 'source_size': list(original.size), 'target': str(target)}


def main() -> None:
    import argparse
    import threading
    import time
    from aipictures.engine import ComfyClient
    from aipictures.storage import write_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--appearance', type=Path)
    parser.add_argument('--prompt', default='')
    parser.add_argument('--negative', default='')
    parser.add_argument('--task', choices=('edit', 'layout', 'repair'), default='edit')
    parser.add_argument('--style', choices=tuple(STYLE_PRESETS), default='custom')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if bool(args.width) != bool(args.height):
        parser.error('--width 和 --height 必须同时提供')
    args.out.mkdir(parents=True, exist_ok=True)
    prepared = prepare_input(args.image, args.out / 'input.png')
    appearance = prepare_input(args.appearance, args.out / 'appearance.png') if args.appearance else None
    client = ComfyClient()
    if args.execute:
        reason = check_models(client.discover()['object_info'])
        if reason:
            raise ValueError(reason)
        prepared = client.upload_image(prepared)
        appearance = client.upload_image(appearance) if appearance else None
    graph = build_workflow(prepared, args.prompt, args.negative, seed=args.seed, task=args.task,
        style=args.style, appearance_reference=appearance,
        size=(args.width, args.height) if args.width else None)
    write_json(args.out / 'workflow.json', graph)
    if args.execute:
        started = time.monotonic()
        result = client.generate(graph, args.out, lambda k,d:print(k,d,flush=True) if k in ('queued','progress') else None,
            threading.Event(), timeout=float('inf'),
            submitted=lambda pid:write_json(args.out / 'submitted.json', {'prompt_id':pid}))
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        write_json(args.out / 'result.json', result)


if __name__ == '__main__':
    main()
