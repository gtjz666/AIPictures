"""Bounded, timestamped visual evidence. Originals and their RGB are never edited."""
import base64
import io
import threading
from pathlib import Path

from PIL import Image, ImageOps

from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest


def image_url(image: Image.Image, side: int = 448) -> str:
    rgba = ImageOps.exif_transpose(image).convert('RGBA')
    rgb = Image.new('RGB', rgba.size, (232, 232, 232))
    rgb.paste(rgba, mask=rgba.getchannel('A'))
    rgb.thumbnail((side, side), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    rgb.save(output, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')


def prepare(reference: Path | None, motion: Path | None, folder: Path, cancel: threading.Event,
            *, role: str = 'appearance', start: float = 0., seconds: float = 8., max_frames: int = 12) -> tuple[list, dict]:
    if role not in ('appearance', 'style', 'edit') or not 2 <= max_frames <= 16:
        raise ValueError('参考用途或识别帧数无效。')
    content, assets = [], []
    if reference:
        reference = Path(reference).resolve(strict=True)
        if reference.stat().st_size > 30 * 1024**2:
            raise ValueError('识别用参考图不能超过30MB。')
        with Image.open(reference) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError('识别参考图过大，请缩小到4000万像素以内。')
            transparent = image.convert('RGBA').getchannel('A').getextrema()[0] < 255
            alpha_note = 'Transparent source; gray is an analysis matte, not a scene.' if transparent else ''
            content += [{'type': 'text', 'text': f'Asset appearance: role={role}. Static target reference. {alpha_note}'},
                        {'type': 'image_url', 'image_url': {'url': image_url(image, 672)}}]
        assets.append(dict(id='appearance', role=role, source=str(reference), sha256=digest(reference),
                           analysis_matte_only=bool(alpha_note)))
    duration = None
    if motion:
        from .motion_guide import inspect, frames
        motion = Path(motion).resolve(strict=True)
        meta = inspect(motion, cancel)
        end = min(meta['duration'], start + seconds)
        if not 0 <= start < end:
            raise ValueError('识别动作片段的起点或长度无效。')
        # Reservoir-free, bounded image storage. Keep the source's held-frame PTS;
        # the final valid source frame is included instead of inventing an endpoint.
        targets = [start + i * (end - start) / max_frames for i in range(max_frames)]
        samples, cursor, last = [], 0, None
        for timestamp, image in frames(motion, cancel):
            if timestamp >= end:
                break
            if last is not None:
                while cursor < len(targets) and targets[cursor] < timestamp:
                    if not samples or samples[-1][0] != last[0]:
                        samples.append(last)
                    cursor += 1
            last = (timestamp, image.copy())
        if last is None:
            raise ValueError('动作素材没有可识别的帧。')
        if not samples or samples[-1][0] != last[0]:
            samples.append(last)
        # At most max_frames; include beginning and ending observations.
        if len(samples) > max_frames:
            samples = [samples[round(i*(len(samples)-1)/(max_frames-1))] for i in range(max_frames)]
        evidence = []
        for i, (timestamp, image) in enumerate(samples):
            if cancel.is_set():
                raise Cancelled('需求识别已取消。')
            content += [{'type': 'text', 'text': f'Asset motion: role=motion only. Frame {i+1}/{len(samples)}, source time {timestamp:.3f}s.'},
                        {'type': 'image_url', 'image_url': {'url': image_url(image, 448)}}]
            target = folder/'evidence'/f'motion_{i:02d}.png'
            target.parent.mkdir(parents=True, exist_ok=True)
            image.thumbnail((448, 448), Image.Resampling.LANCZOS)
            image.save(target)
            evidence.append(dict(time=timestamp, image=str(target)))
        duration = meta['duration']
        assets.append(dict(id='motion', role='motion', source=str(motion), sha256=meta['sha256'],
                           duration=duration, start=start, end=end, frames=evidence))
    metadata = dict(assets=assets, duration=duration, sampled_frame_count=sum(len(a.get('frames', [])) for a in assets),
                    source_rgb_unchanged=True, temporal_blending=False)
    write_json(folder/'evidence.json', metadata)
    return content, metadata
