"""Spatial pixel-grid capture, integer placement and shared palette mapping.

All frames are independent. Resizing, when explicitly requested, uses nearest
neighbour. Quantization is deterministic median cut with no dithering.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
from PIL import Image

from .config import PipelineConfig, PipelineError


def binary_rgba(image: Image.Image, threshold: int) -> tuple[Image.Image, int]:
    rgba = np.array(image.convert("RGBA"))
    fractional = int(((rgba[:, :, 3] > 0) & (rgba[:, :, 3] < 255)).sum())
    rgba[:, :, 3] = np.where(rgba[:, :, 3] >= threshold, 255, 0)
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba), fractional


def extract_palette(images: Sequence[Image.Image], size: int) -> list[list[int]]:
    samples = []
    for image in images:
        rgba = np.asarray(image.convert("RGBA"))
        colors = rgba[:, :, :3][rgba[:, :, 3] > 0]
        # Stable systematic sampling bounds allocation without random subsampling.
        if len(colors):
            samples.append(colors[::max(1, math.ceil(len(colors) / 131072))])
    if not samples:
        return []
    colors = np.concatenate(samples)
    colors = colors[::max(1, math.ceil(len(colors) / 262144))]
    strip = Image.fromarray(colors.reshape(1, -1, 3))
    quantized = strip.quantize(colors=size, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    used = sorted(index for _, index in quantized.getcolors())
    table = np.asarray(quantized.getpalette(), dtype=np.uint8).reshape(-1, 3)
    return [list(color) for color in sorted({tuple(map(int, table[index])) for index in used})]


def map_palette(image: Image.Image, palette: Sequence[Sequence[int]]) -> tuple[Image.Image, dict[str, float]]:
    rgba = np.array(image.convert("RGBA"))
    visible = rgba[:, :, 3] > 0
    colors = rgba[:, :, :3][visible].astype(np.float32)
    if not len(colors):
        return Image.fromarray(rgba), {"mean_rgb_distance": 0.0, "max_rgb_distance": 0.0}
    if not len(palette):
        raise PipelineError("调色板为空，但帧中存在不透明像素；请提供包含主体的锚点图。")
    table = np.asarray(palette, dtype=np.float32)
    result = np.empty_like(colors, dtype=np.uint8)
    distances = []
    for start in range(0, len(colors), 4096):
        block = colors[start:start + 4096]
        squared = ((block[:, None] - table[None]) ** 2).sum(axis=2)
        nearest = squared.argmin(axis=1)
        result[start:start + len(block)] = table[nearest]
        distances.append(np.sqrt(squared[np.arange(len(block)), nearest]) / math.sqrt(3 * 255**2))
    rgba[:, :, :3][visible] = result
    distance = np.concatenate(distances)
    return Image.fromarray(rgba), {"mean_rgb_distance": round(float(distance.mean()), 6),
                                   "max_rgb_distance": round(float(distance.max()), 6)}


def estimate_pixel_size(image: Image.Image) -> tuple[int, float, list[str]]:
    """Find repeating axis edge energy. Ambiguous/sparse edges fall back to one."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    rgb = rgba[:, :, :3] * (rgba[:, :, 3:4] / 255)
    signals = []
    for axis in (0, 1):
        delta = np.abs(np.diff(rgb, axis=axis)).max(axis=2)
        energy = delta.sum(axis=1 if axis == 0 else 0)
        if len(energy) < 12 or energy.max(initial=0) < 1:
            continue
        # Ignore constant gradients; a repeating grid needs several distinct edges.
        peaks = np.flatnonzero((energy[1:-1] >= energy[:-2]) & (energy[1:-1] > energy[2:]) &
                               (energy[1:-1] > energy.mean() + energy.std() * .35)) + 1
        if len(peaks) >= 4:
            signals.append(energy)
    scores: dict[int, float] = {}
    for energy in signals:
        centered = energy - energy.mean()
        for lag in range(2, min(33, len(centered) // 3)):
            a, b = centered[:-lag], centered[lag:]
            correlation = float(np.dot(a, b) / max(1e-8, np.linalg.norm(a) * np.linalg.norm(b)))
            scores[lag] = max(scores.get(lag, -1), correlation)
    if not scores or max(scores.values()) < .45:
        return 1, 0.0, ["像素格估计置信度不足，回退到 1；可用 --pixel-size N 明确指定。"]
    best = max(scores.values())
    # Multiples of the actual grid also correlate; prefer its shortest strong period.
    candidates = [lag for lag, value in scores.items() if value >= max(.45, best * .9)]
    size = min(candidates)
    return size, round(scores[size], 4), ["自动像素格是轴向周期估计，请用最近邻预览确认；倾斜/不规则网格建议手动指定。"]


def merge_axis_transitions(image: Image.Image) -> tuple[Image.Image, int]:
    """Merge rare in-between colors only when flanked by dominant axis colors.

    No convolution or averaging. Each replaced pixel takes an existing neighbour
    color; solid detail regions and silhouettes are not globally filtered.
    """
    rgba = np.array(image)
    visible = rgba[:, :, 3] > 0
    if not visible.any():
        return image, 0
    colors, inverse, counts = np.unique(rgba[:, :, :3][visible], axis=0, return_inverse=True, return_counts=True)
    labels = np.full(visible.shape, -1, dtype=np.int32)
    labels[visible] = inverse
    original = rgba[:, :, :3].astype(np.float32)
    output = rgba.copy()
    changed = np.zeros(visible.shape, dtype=bool)
    for axis in (0, 1):
        for radius in (1, 2):
            if labels.shape[axis] <= radius * 2:
                continue
            center = [slice(None), slice(None)]
            left = center.copy(); right = center.copy()
            center[axis] = slice(radius, -radius)
            left[axis] = slice(None, -2 * radius)
            right[axis] = slice(2 * radius, None)
            c, l, r = tuple(center), tuple(left), tuple(right)
            ci, li, ri = labels[c], labels[l], labels[r]
            valid = (ci >= 0) & (li >= 0) & (ri >= 0) & (ci != li) & (ci != ri) & (li != ri)
            if not valid.any():
                continue
            ci_safe, li_safe, ri_safe = [np.maximum(v, 0) for v in (ci, li, ri)]
            valid &= (counts[ci_safe] * 2 < np.minimum(counts[li_safe], counts[ri_safe]))
            a, b, m = original[l], original[r], original[c]
            vector = b - a
            length = (vector * vector).sum(axis=2)
            t = ((m - a) * vector).sum(axis=2) / np.maximum(length, 1)
            residual = np.linalg.norm(m - (a + t[:, :, None] * vector), axis=2)
            valid &= (length > 400) & (t > .08) & (t < .92) & (residual < 15) & ~changed[c]
            replacement = np.where((t < .5)[:, :, None], a, b).astype(np.uint8)
            output[c][:, :, :3][valid] = replacement[valid]
            changed[c] |= valid
    return Image.fromarray(output), int(changed.sum())


def snap_image(image: Image.Image, config: PipelineConfig) -> tuple[Image.Image, dict[str, Any]]:
    warnings: list[str] = []
    binary, fractional = binary_rgba(image, config.alpha_threshold)
    if fractional:
        warnings.append(f"原图有 {fractional} 个半透明像素，已按阈值 {config.alpha_threshold} 二值化。")
    if np.asarray(image.convert("RGBA"))[:, :, 3].min() == 255:
        warnings.append("输入没有透明背景；本管线不自动抠图，请先去背景，否则背景也会作为素材保留。")
    size, confidence = config.pixel_size, 1.0
    if size == "auto":
        size, confidence, notes = estimate_pixel_size(image)
        warnings.extend(notes)
    size = int(size)
    if size > min(image.size):
        raise PipelineError("pixel_size 大于图片短边；请减小像素格。")
    palette = extract_palette([binary], config.palette_size)
    quantized, _ = map_palette(binary, palette)
    quantized, merged = merge_axis_transitions(quantized)
    array = np.asarray(quantized)
    height, width = array.shape[:2]
    if size == 1:
        warnings.append("像素格为 1：仅量化与局部过渡色归并，不能恢复已经丢失的细节。")
        return quantized, {"input_size": list(image.size), "output_size": list(image.size), "pixel_size": size,
                           "grid_confidence": confidence, "fractional_alpha_pixels": fractional,
                           "merged_transition_pixels": merged, "warnings": warnings}
    small = np.zeros((math.ceil(height / size), math.ceil(width / size), 4), dtype=np.uint8)
    for y in range(small.shape[0]):
        for x in range(small.shape[1]):
            block = array[y * size:(y + 1) * size, x * size:(x + 1) * size]
            visible = block[:, :, 3] > 0
            if visible.sum() * 2 >= visible.size and visible.any():
                colors, counts = np.unique(block[:, :, :3][visible], axis=0, return_counts=True)
                small[y, x, :3] = colors[counts.argmax()]
                small[y, x, 3] = 255
    output = Image.fromarray(small)
    output, merged_small = merge_axis_transitions(output)
    if width % size or height % size:
        warnings.append("输入边长不是像素格的整数倍；末端不足一格按实际覆盖率处理。")
    return output, {"input_size": list(image.size), "output_size": list(output.size), "pixel_size": size,
                    "grid_confidence": confidence, "fractional_alpha_pixels": fractional,
                    "merged_transition_pixels": merged + merged_small, "warnings": warnings}


def bbox_anchor(bbox: tuple[int, int, int, int] | None, mode: str) -> list[float] | None:
    if bbox is None:
        return None
    left, top, right, bottom = bbox
    return [(left + right) / 2, (top + bottom) / 2 if mode == "bbox-center" else float(bottom)]


def normalize_image(image: Image.Image, config: PipelineConfig) -> tuple[Image.Image, dict[str, Any]]:
    source, fractional = binary_rgba(image, config.alpha_threshold)
    original_bbox = source.getchannel("A").getbbox()
    canvas = Image.new("RGBA", (config.canvas_width, config.canvas_height))
    record: dict[str, Any] = {"input_size": list(source.size), "input_bbox": original_bbox,
                              "scale": 1.0, "warnings": []}
    if fractional:
        record["warnings"].append(f"归一化按阈值二值化了 {fractional} 个半透明像素。")
    if original_bbox is None:
        record.update(bbox=None, anchor=None, translation=[0, 0])
        record["warnings"].append("空白透明帧没有可计算的 bbox 锚点。")
        return canvas, record
    bbox = original_bbox
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    factor = min(1., config.canvas_width / width, config.canvas_height / height)
    if factor < 1:
        if not config.allow_scale:
            raise PipelineError(f"主体 {width}×{height} 超出画布 {config.canvas_width}×{config.canvas_height}；增大画布或显式使用 --allow-scale。")
        # Explicit fit changes only this frame; scale is reported so the user can
        # reject inconsistent character size or choose a larger canvas instead.
        source = source.resize((max(1, int(source.width * factor)), max(1, int(source.height * factor))), Image.Resampling.NEAREST)
        bbox = source.getchannel("A").getbbox()
        assert bbox is not None
        record["scale"] = factor
        record["warnings"].append("已明确允许最近邻缩小；不同帧缩放比可能不同，请检查角色比例。")
    if config.anchor_mode == "manual":
        dx, dy = config.manual_offset
    else:
        point = bbox_anchor(bbox, config.anchor_mode)
        assert point is not None
        target = [config.canvas_width / 2, config.canvas_height / 2 if config.anchor_mode == "bbox-center" else config.canvas_height]
        dx, dy = [math.floor(t - p + .5) for t, p in zip(target, point)]
    placed = [bbox[0] + dx, bbox[1] + dy, bbox[2] + dx, bbox[3] + dy]
    if placed[0] < 0 or placed[1] < 0 or placed[2] > canvas.width or placed[3] > canvas.height:
        raise PipelineError("手动偏移会裁掉非透明内容；请调整 manual_offset 或增大画布。")
    # No mask: RGBA replacement preserves independent cells and exact alpha.
    canvas.paste(source.crop(bbox), (placed[0], placed[1]))
    output_bbox = canvas.getchannel("A").getbbox()
    record.update(bbox=output_bbox, anchor=bbox_anchor(output_bbox, config.anchor_mode), translation=[dx, dy])
    return canvas, record
