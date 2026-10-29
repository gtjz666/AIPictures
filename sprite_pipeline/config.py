"""Validated generation and postprocess settings. No model or backend imports."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


class PipelineError(ValueError):
    """An actionable configuration or input error."""


@dataclass(frozen=True)
class PipelineConfig:
    canvas_width: int = 64
    canvas_height: int = 64
    anchor_mode: str = "bottom-center"
    palette_size: int = 24
    pixel_size: int | str = "auto"
    seed: int | None = None
    anchor: str | None = None
    padding: int = 0
    columns: int | None = None
    rows: int | None = None
    fps: float = 8.0
    alpha_threshold: int = 128
    allow_scale: bool = False
    manual_offset: tuple[int, int] = (0, 0)
    drift_threshold: float = 1.0
    palette_distance_threshold: float = 0.08

    def validate(self, check_anchor: bool = True) -> PipelineConfig:
        for name in ("canvas_width", "canvas_height", "palette_size", "alpha_threshold"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise PipelineError(f"{name} 必须为正整数。")
        if max(self.canvas_width, self.canvas_height) > 16384:
            raise PipelineError("画布单边不能超过 16384；请使用精灵单帧尺寸。")
        if self.palette_size > 256 or self.alpha_threshold > 255:
            raise PipelineError("palette_size 范围 1–256，alpha_threshold 范围 1–255。")
        if self.anchor_mode not in ("bottom-center", "bbox-center", "manual"):
            raise PipelineError("anchor_mode 请选择 bottom-center / bbox-center / manual。")
        if self.pixel_size != "auto" and (type(self.pixel_size) is not int or self.pixel_size < 1):
            raise PipelineError("pixel_size 请选择 auto 或正整数。")
        if self.seed is not None and (type(self.seed) is not int or not 0 <= self.seed < 2**64):
            raise PipelineError("seed 必须是固定整数 0–2^64-1；不接受 -1 随机。")
        if self.anchor is not None:
            if not isinstance(self.anchor, str) or not self.anchor:
                raise PipelineError("anchor 必须是图片路径或 null。")
            if check_anchor and not Path(self.anchor).is_file():
                raise PipelineError(f"找不到锚点图：{self.anchor}，请修正 anchor 路径。")
        if type(self.padding) is not int or self.padding < 0:
            raise PipelineError("padding 必须是非负整数。")
        for name in ("columns", "rows"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 1):
                raise PipelineError(f"{name} 必须是正整数或 null。")
        if type(self.allow_scale) is not bool:
            raise PipelineError("allow_scale 必须是 true / false。")
        if not isinstance(self.manual_offset, (tuple, list)) or len(self.manual_offset) != 2 or any(type(v) is not int for v in self.manual_offset):
            raise PipelineError("manual_offset 必须是两个整数 [dx, dy]。")
        for name in ("fps", "drift_threshold", "palette_distance_threshold"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise PipelineError(f"{name} 必须是有限非负数。")
        if self.fps == 0 or self.palette_distance_threshold > 1:
            raise PipelineError("fps 必须大于 0；palette_distance_threshold 范围 0–1。")
        return self

    def document(self) -> dict[str, Any]:
        return asdict(self)


def load_config(path: str | Path) -> PipelineConfig:
    path = Path(path).resolve()
    try:
        if path.suffix.lower() in (".yaml", ".yml"):
            import yaml
            try:
                data = yaml.safe_load(path.read_text("utf-8-sig"))
            except yaml.YAMLError as exc:
                raise PipelineError(f"YAML 格式错误：{path}：{exc}") from exc
        else:
            data = json.loads(path.read_text("utf-8-sig"))
    except ImportError as exc:
        raise PipelineError("读取 YAML 需要 PyYAML：pip install PyYAML。也可使用 JSON。") from exc
    except (OSError, ValueError) as exc:
        raise PipelineError(f"读取配置失败：{path}：{exc}") from exc
    # YAML parser errors are ValueError-independent; expose a concise CLI error.
    if not isinstance(data, dict):
        raise PipelineError("配置必须是 JSON 对象或 YAML 映射。")
    unknown = set(data) - {f.name for f in fields(PipelineConfig)}
    if unknown:
        raise PipelineError("未知配置字段：" + ", ".join(sorted(unknown)))
    if data.get("anchor"):
        if not isinstance(data["anchor"], str):
            raise PipelineError("anchor 必须是图片路径。")
        data["anchor"] = str((path.parent / data["anchor"]).resolve())
    return PipelineConfig(**data).validate()


def write_document(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    # Replace only this known output file; readers never see a partial document.
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
