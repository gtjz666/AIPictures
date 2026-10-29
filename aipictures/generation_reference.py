"""Build the model's reference from source pixels, independently of pose masks.

Segmentation is useful for locating joints. Its cleaned alpha/RGB must never
become the appearance input implicitly. Existing source alpha is composited
once onto a neutral backing; no segmentation or color repair runs here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

BACKGROUND = (242, 243, 245)


def prepare_generation_reference(
    source: str | Path, target: str | Path, analysis: dict[str, Any],
) -> dict[str, Any]:
    """Apply the pose analysis placement, while keeping unsegmented source RGB.

    Keep the complete source canvas, including its original background. Only
    pixels beyond the animation canvas are clipped. Mirroring follows the same
    canonical direction as the skeleton and is undone at export.
    """
    geometry = analysis.get('geometry')
    if not geometry:
        raise ValueError('骨骼分析缺少参考图排版数据，请重新分析参考图后生成。')
    box = geometry['source_bbox']
    x, y = geometry['offset']
    bounds = geometry['subject_bbox']
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    if width <= 0 or height <= 0 or box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError('参考图排版尺寸无效，请重新分析参考图。')
    size = tuple(analysis.get('canvas', (768, 1024)))
    with Image.open(source) as original:
        rgba = ImageOps.exif_transpose(original).convert('RGBA')
    # Match the subject placement exactly. Separate surrounding strips retain
    # source background without allowing their resampling grid to move the body.
    canvas = Image.new('RGBA', size, (*BACKGROUND, 255))
    sx, sy = width / (box[2] - box[0]), height / (box[3] - box[1])
    full = rgba.resize((max(1, round(rgba.width * sx)), max(1, round(rgba.height * sy))),
                       Image.Resampling.LANCZOS)
    canvas.alpha_composite(full, (round(x - box[0] * sx), round(y - box[1] * sy)))
    subject = rgba.crop(tuple(box)).resize((width, height), Image.Resampling.LANCZOS)
    # Overwrite this area against the backing so fractional source alpha is
    # composited once, rather than accumulated over the full-image layer.
    backing = Image.new('RGBA', subject.size, (*BACKGROUND, 255))
    backing.alpha_composite(subject)
    canvas.paste(backing, (x, y))
    if analysis.get('direction') == 'left':
        canvas = ImageOps.mirror(canvas)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert('RGB').save(target)
    return {
        'path': str(target), 'source': str(source),
        'policy': 'source_pixels_before_output_matting',
        'segmentation_applied': False, 'color_repair_applied': False,
        'existing_alpha': 'composited_once_on_neutral_background',
        'background': list(BACKGROUND), 'canvas': list(size),
        'geometry': geometry, 'mirrored': analysis.get('direction') == 'left',
        'transparency_stage': 'after_animation_generation',
    }
