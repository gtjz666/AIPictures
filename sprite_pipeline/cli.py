"""Standalone command line. Paths with spaces are supported as normal arguments."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .config import PipelineConfig, PipelineError, load_config, write_document
from .pipeline import read_state, run_pipeline, run_stage
from .validation import validate_output


def _options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, help="JSON/YAML；相对 anchor 路径以配置所在目录为准")
    parser.add_argument("--canvas-width", type=int)
    parser.add_argument("--canvas-height", type=int)
    parser.add_argument("--anchor-mode", choices=("bottom-center", "bbox-center", "manual"))
    parser.add_argument("--anchor", type=Path)
    parser.add_argument("--pixel-size", help="auto 或正整数，整段使用同一网格")
    parser.add_argument("--palette-size", type=int)
    parser.add_argument("--alpha-threshold", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--padding", type=int)
    parser.add_argument("--columns", type=int)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--manual-offset", type=int, nargs=2, metavar=("DX", "DY"))
    parser.add_argument("--drift-threshold", type=float)
    parser.add_argument("--palette-distance-threshold", type=float)
    parser.add_argument("--allow-scale", action="store_true", default=None, help="明确允许最近邻缩小超出画布的内容")


def _config(args: argparse.Namespace) -> PipelineConfig:
    if args.config:
        config = load_config(args.config)
    elif getattr(args, "command", "") != "config" and (Path(args.out) / "pipeline.json").is_file():
        config = load_config(Path(args.out) / "pipeline.json")
    elif getattr(args, "command", "") != "config" and (Path(args.out) / "pipeline-state.json").is_file():
        config = PipelineConfig(**read_state(Path(args.out))["pipeline"])
    else:
        config = PipelineConfig()
    changes = {}
    for key in config.document():
        value = getattr(args, key, None)
        if value is not None:
            if key == "anchor":
                value = str(value.resolve())
            if key == "pixel_size" and value != "auto":
                try:
                    value = int(value)
                except ValueError as exc:
                    raise PipelineError("--pixel-size 只能为 auto 或正整数。") from exc
            changes[key] = value
    return replace(config, **changes).validate()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sprite_pipeline", description="离散精灵帧：像素捕捉 → 锚点归一化 → 共享调色板 → 拼图 → 验收")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("snap", "normalize", "palette", "assemble", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("input", type=Path, help="PNG 帧目录；不递归")
        sub.add_argument("--out", type=Path, required=True)
        _options(sub)
    validate = commands.add_parser("validate")
    validate.add_argument("--out", type=Path, required=True)
    _options(validate)
    config = commands.add_parser("config", help="生成或校验生成阶段约束；不会运行 AI")
    config.add_argument("--out", type=Path, help="写 pipeline.yaml 或 pipeline.json")
    config.add_argument("--check", type=Path, help="只校验已有配置")
    _options(config)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "config":
            if args.check:
                config = load_config(args.check)
                if config.seed is None:
                    raise PipelineError("生成阶段配置必须指定固定 seed。")
                print(json.dumps({"pass": True, "config": config.document()}, ensure_ascii=False, indent=2))
                return 0
            if not args.out:
                raise PipelineError("生成配置需要 --out pipeline.yaml；校验请用 --check pipeline.yaml。")
            config = _config(args)
            if config.seed is None:
                raise PipelineError("请用 --seed 指定固定整数；后处理不会代替生成阶段锁定种子。")
            write_document(args.out, config.document())
            print("已写入配置：" + str(args.out.resolve()))
            return 0
        config = _config(args)
        if args.command == "validate":
            result = validate_output(args.out, config)
        elif args.command == "run":
            result = run_pipeline(args.input, args.out, config)
        else:
            result = run_stage(args.command, args.input, args.out, config)
        summary = {k: v for k, v in result.items() if k in ("pass", "stage", "frames", "out", "warnings") and k != "frames"}
        if isinstance(result.get("frames"), int):
            summary["frames"] = result["frames"]
        summary["report"] = str((args.out / "report.json").resolve())
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if result.get("pass", True) else 1
    except (PipelineError, OSError, ValueError) as exc:
        print("sprite_pipeline：" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
