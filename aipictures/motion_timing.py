"""Map observed source intervals onto the selected output clock, without retiming."""
import math


def clip_rows(rows: list[dict], start: float, end: float, *, shift: float = 0.) -> list[dict]:
    """Intersect intervals with a window. Descriptions and playback speed stay intact."""
    result = []
    for row in rows:
        left, right = max(start, float(row['start'])), min(end, float(row['end']))
        if right > left + 1e-9:
            result.append(dict(start=left + shift, end=right + shift, description=row['description']))
    return result


def source_to_output(rows: list[dict], source_seconds: float, output_seconds: float,
                     *, start: float = 0., repeat: bool = False, hold_tail: bool = True) -> list[dict]:
    """Use the guide's start + output time, wrapping only when repeat is selected.

    No stretching, interpolation, or image processing occurs here. Unknown source
    intervals remain gaps; they must not become invented motion descriptions.
    """
    if not all(math.isfinite(v) for v in (source_seconds, output_seconds, start)) or not (
            source_seconds > 0 and output_seconds > 0 and 0 <= start < source_seconds):
        raise ValueError('动作时间映射需要有效的素材时长、输出时长和素材范围内的起点。')
    result = []
    cycles = math.ceil((start + output_seconds) / source_seconds) if repeat else 1
    for cycle in range(cycles):
        offset = cycle * source_seconds - start
        shifted = [dict(row, start=float(row['start']) + offset, end=float(row['end']) + offset) for row in rows]
        result.extend(clip_rows(shifted, 0., output_seconds))
    remaining = source_seconds - start
    if not repeat and hold_tail and remaining < output_seconds:
        result.append(dict(start=remaining, end=output_seconds, description='保持参考末帧可见姿势'))
    return result
