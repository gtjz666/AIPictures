"""Disk stages, provenance and lossless sprite sheet assembly."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

from .config import PipelineConfig, PipelineError, write_document
from .pixels import binary_rgba, bbox_anchor, extract_palette, map_palette, normalize_image, snap_image

SCHEMA_VERSION = 1
StageCallback = Callable[[str, int, int], None]


def natural_key(path: Path) -> list[tuple[int, Any]]:
    return [(0, int(part)) if part.isdigit() else (1, part.casefold()) for part in re.split(r"(\d+)", path.name)] + [(2, path.name)]


def frame_paths(directory: str | Path, anchor: str | None = None) -> list[Path]:
    root = Path(directory).resolve()
    if not root.is_dir():
        raise PipelineError(f"输入目录不存在：{root}")
    excluded = Path(anchor).resolve() if anchor else None
    paths = sorted((p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".png" and p.resolve() != excluded), key=natural_key)
    if not paths:
        raise PipelineError(f"输入目录没有 PNG 帧：{root}（锚点图不作为动画帧）。")
    return paths


def read_state(out: Path) -> dict[str, Any]:
    path = out / "pipeline-state.json"
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "stages": {}, "warnings": [], "sources": {}}
    try:
        state = json.loads(path.read_text("utf-8"))
        if state["schema_version"] != SCHEMA_VERSION or not isinstance(state["stages"], dict):
            raise ValueError("unsupported schema")
        return state
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PipelineError(f"无法读取已有管线状态 {path}；请改用新的输出目录。") from exc


def _prepare(directory: str | Path, out: str | Path, config: PipelineConfig) -> tuple[list[Path], Path, dict[str, Any]]:
    config.validate()
    paths = frame_paths(directory, config.anchor)
    out = Path(out).resolve()
    if Path(directory).resolve() == out:
        raise PipelineError("输入目录不能就是输出根目录；请指定独立的 --out。分步操作可输入 out/frames。")
    if config.anchor and Path(config.anchor).resolve().is_relative_to(out / "frames"):
        raise PipelineError("锚点图不能放在会被写入的 out/frames 内；请将锚点移到输入目录或其他位置。")
    state = read_state(out)
    frames = out / "frames"
    existing = set(p.name for p in frames.glob("*.png")) if frames.exists() else set()
    owned = set(state.get("output_frames", []))
    if existing - owned:
        raise PipelineError("输出 frames 目录有不属于本管线的 PNG；为防止覆盖，请换新的 --out 目录。")
    for path in paths:
        if path.name not in state["sources"] or path.parent != frames:
            state["sources"][path.name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return paths, out, state


def _read_images(paths: list[Path]) -> list[Image.Image]:
    images = []
    for path in paths:
        try:
            with Image.open(path) as source:
                images.append(source.convert("RGBA"))
        except (OSError, ValueError) as exc:
            raise PipelineError(f"无法读取 PNG：{path}：{exc}") from exc
    return images


def _write_frames(out: Path, paths: list[Path], images: list[Image.Image], state: dict[str, Any]) -> None:
    frames = out / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    for path, image in zip(paths, images):
        temporary = frames / (path.name + ".tmp")
        image.save(temporary, format="PNG")
        temporary.replace(frames / path.name)
    names = [p.name for p in paths]
    # Only previously registered output names, never enumerate/delete arbitrary inputs.
    for name in set(state.get("output_frames", [])) - set(names):
        stale = frames / name
        if stale.parent == frames and stale.is_file():
            stale.unlink()
    state["output_frames"] = names


def _record(out: Path, state: dict[str, Any], stage: str, config: PipelineConfig, records: list[dict[str, Any]], warnings: list[str]) -> None:
    state["pipeline"] = config.document()
    state["stages"][stage] = {"parameters": config.document(), "frames": records}
    state["warnings"] = list(dict.fromkeys(state["warnings"] + warnings))
    write_document(out / "pipeline-state.json", state)
    write_document(out / "pipeline.json", config.document())
    # Until validation, do not present an earlier pass as the new result.
    write_document(out / "report.json", {"schema_version": SCHEMA_VERSION, "pass": False, "status": "not_validated",
                   "warnings": state["warnings"], "stages": state["stages"]})


def run_stage(stage: str, directory: str | Path, out: str | Path, config: PipelineConfig,
              progress: StageCallback | None = None) -> dict[str, Any]:
    try:
        return _run_stage(stage, directory, out, config, progress)
    except (OSError, ValueError) as exc:
        output = Path(out).resolve()
        # Only update a directory we have already initialized, and never write
        # into a rejected source root. Failed stages cannot leave a stale pass.
        if output != Path(directory).resolve() and (output / "pipeline-state.json").is_file():
            try:
                state = read_state(output)
                write_document(output / "report.json", {"schema_version": SCHEMA_VERSION, "pass": False,
                    "status": "processing_failed", "stage": stage, "error": str(exc),
                    "warnings": state.get("warnings", []), "stages": state.get("stages", {})})
            except (OSError, ValueError):
                pass
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError(f"{stage} 处理失败：{exc}") from exc


def _run_stage(stage: str, directory: str | Path, out: str | Path, config: PipelineConfig,
               progress: StageCallback | None = None) -> dict[str, Any]:
    if stage not in ("snap", "normalize", "palette", "assemble"):
        raise PipelineError(f"未知阶段：{stage}")
    paths, out, state = _prepare(directory, out, config)
    images = _read_images(paths)
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    processed: list[Image.Image] = []
    if stage == "snap" and config.pixel_size == "auto":
        from .pixels import estimate_pixel_size
        with Image.open(config.anchor or paths[0]) as reference:
            size, confidence, notes = estimate_pixel_size(reference)
        state["grid_estimation"] = {"pixel_size": size, "confidence": confidence,
                                    "source": config.anchor or str(paths[0]), "warnings": notes}
        warnings.extend(notes)
        config = replace(config, pixel_size=size)
    if stage == "palette":
        binary = [binary_rgba(image, config.alpha_threshold)[0] for image in images]
        if config.anchor:
            with Image.open(config.anchor) as anchor:
                # Quantize the same visible reference colors, not target-frame colors.
                anchor_image = binary_rgba(anchor, config.alpha_threshold)[0]
            colors = extract_palette([anchor_image], config.palette_size)
            origin = "anchor"
            anchor_digest = hashlib.sha256(Path(config.anchor).read_bytes()).hexdigest()
        else:
            colors = extract_palette(binary, config.palette_size)
            origin, anchor_digest = "sequence", None
            warnings.append("未提供锚点图，使用全序列共同调色板；无法证明与生成阶段角色配色一致。")
        state["palette"] = {"colors": colors, "origin": origin, "anchor": config.anchor, "anchor_sha256": anchor_digest,
                            "size_limit": config.palette_size, "distance_metric": "sRGB Euclidean / (255 * sqrt(3)); range 0..1"}
        for path, image in zip(paths, binary):
            result, distances = map_palette(image, colors)
            records.append({"file": path.name, **distances})
            processed.append(result)
            if distances["mean_rgb_distance"] > config.palette_distance_threshold:
                warnings.append(f"{path.name} 映射前与基准调色板的平均色差 {distances['mean_rgb_distance']:.4f} 超过阈值，可能存在错色或细节丢失。")
            if progress:
                progress(stage, len(records), len(paths))
    elif stage in ("snap", "normalize"):
        operation = snap_image if stage == "snap" else normalize_image
        for path, image in zip(paths, images):
            result, record = operation(image, config)
            records.append({"file": path.name, **record})
            warnings.extend(f"{path.name}：{note}" for note in record["warnings"])
            processed.append(result)
            if progress:
                progress(stage, len(records), len(paths))
    else:
        processed = images
    # All images must be computed successfully before changing an existing output.
    if stage == "assemble":
        metadata = assemble_images(out, paths, processed, config, state)
        state["sheet"] = "sprite_sheet.json"
        records = metadata["frames"]
    _write_frames(out, paths, processed, state)
    if stage == "palette":
        write_document(out / "palette.json", state["palette"])
    _record(out, state, stage, config, records, warnings)
    return {"out": str(out), "frames": len(paths), "stage": stage, "warnings": warnings}


def assemble_images(out: Path, paths: list[Path], images: list[Image.Image], config: PipelineConfig,
                    state: dict[str, Any]) -> dict[str, Any]:
    expected = (config.canvas_width, config.canvas_height)
    if any(image.size != expected for image in images):
        raise PipelineError(f"拼图需要每帧均为 {expected[0]}×{expected[1]}；请先运行 normalize。")
    count = len(images)
    columns, rows = config.columns, config.rows
    if columns is None and rows is None:
        columns = math.ceil(math.sqrt(count))
    if columns is None:
        columns = math.ceil(count / rows)  # type: ignore[operator]
    if rows is None:
        rows = math.ceil(count / columns)
    if columns * rows < count:
        raise PipelineError(f"网格 {columns}×{rows} 容不下 {count} 帧；增加 columns/rows 或留空自动计算。")
    pad, width, height = config.padding, *expected
    sheet_size = (columns * width + (columns + 1) * pad, rows * height + (rows + 1) * pad)
    if sheet_size[0] * sheet_size[1] > 100_000_000:
        raise PipelineError("精灵图超过一亿像素；请减少行列、画布或拆分序列。")
    sheet = Image.new("RGBA", sheet_size)
    records = []
    for index, (path, image) in enumerate(zip(paths, images)):
        x = pad + index % columns * (width + pad)
        y = pad + index // columns * (height + pad)
        sheet.paste(image, (x, y))
        bbox = image.getchannel("A").getbbox()
        records.append({"index": index, "name": path.name, "file": "frames/" + path.name,
                        "source": state["sources"][path.name], "rect": {"x": x, "y": y, "w": width, "h": height},
                        "bbox": bbox, "anchor": bbox_anchor(bbox, config.anchor_mode)})
    out.mkdir(parents=True, exist_ok=True)
    sheet.save(out / "sprite_sheet.png")
    metadata = {"schema_version": SCHEMA_VERSION, "image": "sprite_sheet.png", "frame_width": width, "frame_height": height,
                "frame_count": count, "columns": columns, "rows": rows, "padding": pad, "fps": config.fps,
                "anchor": {"mode": config.anchor_mode, "coordinate_space": "frame; bbox bottom/right are exclusive",
                           "target": [width / 2, height / 2 if config.anchor_mode == "bbox-center" else height] if config.anchor_mode != "manual" else None,
                           "manual_offset": list(config.manual_offset)},
                "palette": state.get("palette", {}).get("colors", []), "frames": records,
                "pipeline": config.document(), "stages": state["stages"],
                "generation": {"seed": config.seed, "anchor": config.anchor,
                               "note": "Recorded constraints only; postprocessing does not regenerate frames or verify model compliance."}}
    write_document(out / "sprite_sheet.json", metadata)
    return metadata


def run_pipeline(directory: str | Path, out: str | Path, config: PipelineConfig,
                 progress: StageCallback | None = None) -> dict[str, Any]:
    """Capture -> normalize -> align palette -> assemble -> validate."""
    config.validate()
    paths = frame_paths(directory, config.anchor)
    # A single sequence uses one grid, estimated from its anchor or first frame.
    # Per-frame auto estimation could otherwise change character size over time.
    grid_note: dict[str, Any] = {}
    effective = config
    if config.pixel_size == "auto":
        from .pixels import estimate_pixel_size
        with Image.open(config.anchor or paths[0]) as reference:
            size, confidence, warnings = estimate_pixel_size(reference)
        effective = replace(config, pixel_size=size)
        grid_note = {"pixel_size": size, "confidence": confidence, "source": config.anchor or str(paths[0]), "warnings": warnings}
    run_stage("snap", directory, out, effective, progress)
    out = Path(out).resolve()
    if grid_note:
        state = read_state(out)
        state["grid_estimation"] = grid_note
        state["warnings"].extend(grid_note["warnings"])
        write_document(out / "pipeline-state.json", state)
    for stage in ("normalize", "palette", "assemble"):
        run_stage(stage, out / "frames", out, effective, progress)
    from .validation import validate_output
    return validate_output(out, effective)
