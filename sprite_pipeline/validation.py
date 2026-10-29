"""Asset checks. Structural passes are not a guarantee of AI anatomy/identity."""
from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .config import PipelineConfig, PipelineError, load_config, write_document
from .pixels import binary_rgba, bbox_anchor, extract_palette, map_palette


def audit_processing_code(package: Path | None = None) -> dict[str, Any]:
    """Inspect executable imports/calls and dependency manifests, not prose labels."""
    package = package or Path(__file__).parent
    forbidden = {"fxaa", "taa", "dlss", "gaussianblur", "gaussian_filter", "blend", "accumulateweighted"}
    findings: list[str] = []
    inspected: list[str] = []
    for path in sorted(package.glob("*.py")):
        inspected.append(path.name)
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [entry.name for entry in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [entry.name for entry in node.names]
            elif isinstance(node, ast.Call):
                func = node.func
                names = [func.attr if isinstance(func, ast.Attribute) else func.id] if isinstance(func, (ast.Attribute, ast.Name)) else []
            for name in names:
                if set(re.split(r"[.\-_]", name.casefold())) & forbidden:
                    findings.append(f"{path.name}:{node.lineno}：禁止的导入/调用 {name}")
    # In installed wheels the repository manifests can be absent. importlib metadata
    # still checks the actual packaged runtime requirements in that case.
    manifests = []
    for name in ("pyproject.toml", "requirements.txt", "requirements-lock.txt"):
        path = package.parent / name
        if path.is_file():
            manifests.append(name)
            for line in path.read_text("utf-8").splitlines():
                if line.lstrip().startswith("#"):
                    continue
                for token in ("fxaa", "taa", "dlss"):
                    if re.search(r"(?<![a-z])" + token + r"(?![a-z])", line, re.I):
                        findings.append(f"{name}：禁止的依赖标记 {token}")
    if not manifests:
        from importlib.metadata import PackageNotFoundError, requires
        try:
            dependencies = requires("aipictures-sprite-pipeline") or []
            manifests.append("installed package requirements")
            for dependency in dependencies:
                if re.search(r"\b(?:fxaa|taa|dlss)\b", dependency, re.I):
                    findings.append("禁止的依赖：" + dependency)
        except PackageNotFoundError:
            findings.append("找不到依赖清单；请使用仓库源码或安装 sprite_pipeline 包后验收。")
    return {"pass": not findings, "files": inspected, "dependency_manifests": manifests, "findings": findings,
            "scope": "sprite_pipeline executable imports/calls and runtime dependency manifests; not a proof against arbitrary obfuscation"}


def validate_output(out: str | Path, config: PipelineConfig | None = None) -> dict[str, Any]:
    from .pipeline import frame_paths, read_state
    out = Path(out).resolve()
    state = read_state(out)
    if config is None:
        if (out / "pipeline.json").is_file():
            config = load_config(out / "pipeline.json")
        elif "pipeline" in state:
            config = PipelineConfig(**state["pipeline"])
        else:
            raise PipelineError("找不到处理参数；请先运行 run/assemble，或向 validate 提供 --config。")
    config.validate(check_anchor=False)
    paths = frame_paths(out / "frames")
    checks: dict[str, Any] = {}
    warnings = list(state.get("warnings", []))
    records = []
    expected = (config.canvas_width, config.canvas_height)
    images: dict[str, np.ndarray] = {}
    anchors = []
    color_sets: list[set[tuple[int, ...]]] = []
    palette_colors = state.get("palette", {}).get("colors", [])
    palette_set = {tuple(v) for v in palette_colors}
    for path in paths:
        with Image.open(path) as source:
            image = source.convert("RGBA")
        array = np.asarray(image)
        images[path.name] = array
        visible = array[:, :, 3] > 0
        unique = np.unique(array[:, :, :3][visible], axis=0)
        color_sets.append({tuple(map(int, color)) for color in unique})
        bbox = image.getchannel("A").getbbox()
        point = bbox_anchor(bbox, config.anchor_mode)
        if point is None:
            warnings.append(f"{path.name} 是空白透明帧，不参与锚点漂移统计。")
        else:
            anchors.append(point)
        records.append({"file": path.name, "size": list(image.size), "bbox": bbox, "anchor": point,
                        "unique_colors": len(unique), "binary_alpha": bool(np.isin(array[:, :, 3], (0, 255)).all()),
                        "colors_outside_shared_palette": sum(tuple(v) not in palette_set for v in unique)})
    checks["frame_dimensions"] = {"pass": all(tuple(r["size"]) == expected for r in records), "expected": list(expected)}
    checks["color_count"] = {"pass": all(r["unique_colors"] <= config.palette_size for r in records), "limit": config.palette_size}
    checks["binary_alpha"] = {"pass": all(r["binary_alpha"] for r in records)}
    checks["shared_palette"] = {"pass": bool(palette_colors) and all(r["colors_outside_shared_palette"] == 0 for r in records),
                                "colors": palette_colors}
    usage = []
    for index in range(1, len(color_sets)):
        previous, current = color_sets[index - 1:index + 1]
        union = previous | current
        usage.append({"from": paths[index - 1].name, "to": paths[index].name,
                      "palette_usage_jaccard_distance": round(1 - len(previous & current) / len(union), 6) if union else 0.,
                      "note": "Color usage changes can be legitimate occlusion or pose changes, not necessarily palette drift."})
    checks["frame_palette_usage"] = {"pass": True, "adjacent_frames": usage}
    # An all-transparent sequence can legitimately have an empty palette.
    if all(r["unique_colors"] == 0 for r in records):
        checks["shared_palette"]["pass"] = True
        warnings.append("整组序列为空白；结构可验收，但不能作为可见角色素材。")
    checks["no_global_or_temporal_filter"] = audit_processing_code()
    slicing_errors = []
    try:
        metadata = json.loads((out / "sprite_sheet.json").read_text("utf-8"))
        with Image.open(out / "sprite_sheet.png") as sheet_source:
            sheet = sheet_source.convert("RGBA")
        entries = metadata["frames"]
        if [e["name"] for e in entries] != [p.name for p in paths] or metadata["frame_count"] != len(paths):
            slicing_errors.append("metadata 帧列表、数量或自然排序与 frames 不一致。")
        if (metadata["frame_width"], metadata["frame_height"]) != expected:
            slicing_errors.append("metadata 单帧尺寸与管线参数不一致。")
        occupied: list[tuple[int, int, int, int]] = []
        for entry in entries:
            rect = entry["rect"]
            x, y, width, height = (rect[k] for k in ("x", "y", "w", "h"))
            if entry["file"] != "frames/" + entry["name"] or (width, height) != expected:
                slicing_errors.append(f"{entry['name']} 的单帧路径或矩形尺寸与配置不一致。")
            if any(type(v) is not int for v in (x, y, width, height)) or x < 0 or y < 0 or width < 1 or height < 1 or x + width > sheet.width or y + height > sheet.height:
                slicing_errors.append(f"{entry['name']} 的切片矩形越界或无效。")
                continue
            region = (x, y, x + width, y + height)
            if any(x < r[2] and x + width > r[0] and y < r[3] and y + height > r[1] for r in occupied):
                slicing_errors.append("切片矩形发生重叠。")
            occupied.append(region)
            readback = np.asarray(sheet.crop(region))
            if entry["name"] not in images or not np.array_equal(readback, images[entry["name"]]):
                slicing_errors.append(f"{entry['name']} 切片回读与单帧像素不一致。")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        slicing_errors.append("读取精灵图/metadata 失败：" + str(exc))
    checks["sheet_roundtrip"] = {"pass": not slicing_errors, "errors": slicing_errors}
    drift = float(np.linalg.norm(np.ptp(np.asarray(anchors), axis=0))) if anchors else 0.0
    checks["anchor_drift"] = {"pass": True, "within_threshold": drift <= config.drift_threshold,
                              "max_extent_pixels": round(drift, 4), "threshold": config.drift_threshold,
                              "scope": "alpha bbox anchor; not semantic skeleton feet or an animation quality score"}
    if drift > config.drift_threshold:
        warnings.append(f"bbox 锚点漂移 {drift:.2f}px 超过 {config.drift_threshold}px；请检查脚底、阴影、跳跃或手动偏移。")
    if len(anchors) > 1 and config.anchor_mode == "bottom-center":
        warnings.append("bottom-center 按轮廓脚底逐帧贴底；跳跃/位移动画应使用 manual 保留原始轨迹。")
    anchor_comparison: dict[str, Any] = {"pass": True, "available": False}
    if config.anchor:
        if not Path(config.anchor).is_file():
            warnings.append("锚点图已移动，无法重新验收锚点调色板。")
        else:
            with Image.open(config.anchor) as source:
                anchor = binary_rgba(source, config.alpha_threshold)[0]
            reference_palette = extract_palette([anchor], config.palette_size)
            frame_distances = []
            for path in paths:
                with Image.open(path) as image:
                    _, distances = map_palette(image, reference_palette)
                frame_distances.append({"file": path.name, **distances})
            maximum_mean = max((r["mean_rgb_distance"] for r in frame_distances), default=0.)
            anchor_comparison["pass"] = maximum_mean <= config.palette_distance_threshold
            anchor_comparison.update(available=True,
                                     within_threshold=maximum_mean <= config.palette_distance_threshold,
                                     maximum_frame_mean_rgb_distance=maximum_mean, threshold=config.palette_distance_threshold,
                                     reference_palette=reference_palette, frames=frame_distances)
            if maximum_mean > config.palette_distance_threshold:
                warnings.append("输出配色与锚点调色板差异超限；请重新运行 palette，或检查是否换错锚点图。")
    else:
        warnings.append("没有锚点图，跳过独立锚点调色板差异检查。")
    checks["anchor_palette_distance"] = anchor_comparison
    if config.seed is None:
        warnings.append("未记录固定 seed；后处理不会重新生成，也不能补证生成阶段是否锁定构图。")
    checks["generation_config"] = {"pass": True, "seed": config.seed, "fixed_seed_recorded": config.seed is not None,
                                   "anchor_recorded": bool(config.anchor), "model_compliance_verified": False}
    report = {"schema_version": 1, "pass": all(c["pass"] for c in checks.values()), "checks": checks,
              "warnings": list(dict.fromkeys(warnings)), "frames": records, "pipeline": config.document(),
              "stages": state.get("stages", {}), "grid_estimation": state.get("grid_estimation"),
              "limitations": ["结构验收不证明角色身份、肢体数量、绘画细节或动作正确；需要逐帧目视验收。",
                              "调色板近邻映射不识别衣服/皮肤区域，不能把错放的颜色自动填回语义部位。"]}
    write_document(out / "report.json", report)
    return report
