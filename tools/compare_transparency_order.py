"""Repeat an existing Wan job with only its reference preparation changed.

Usage: python -m tools.compare_transparency_order --sequence PATH --out PATH
Add --execute to submit the recorded graph to the existing local backend.
The original workflow, seed, poses and raw outputs remain untouched.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlencode

import numpy as np
from PIL import Image, ImageDraw

from aipictures.background import foreground_rgba, release_session, MODEL as MATTE_MODEL
from aipictures.engine import ComfyClient
from aipictures.generation_reference import prepare_generation_reference
from aipictures.storage import write_json
from aipictures.workflow_library import digest


def download_completed(client: ComfyClient, prompt_id: str, folder: Path) -> dict:
    """Resume a completed experiment without submitting another generation."""
    history = client.request('/history/' + prompt_id, timeout=120).get(prompt_id)
    if not history or history.get('status', {}).get('status_str') != 'success':
        raise ValueError('该任务尚未成功完成，请等待后再恢复下载。不会自动重新生成。')
    folder.mkdir(parents=True, exist_ok=True)
    result = {'prompt_id': prompt_id, 'images': [], 'latents': [], 'history': history}
    for output in history.get('outputs', {}).values():
        for field, stem, suffix in (('images', 'image', '.png'), ('latents', 'samples', '.latent')):
            for item in output.get(field, []):
                if item.get('type', 'output') != 'output':
                    continue
                path = folder / f'{stem}_{len(result[field]):03d}{suffix}'
                path.write_bytes(client.request('/view?' + urlencode(item), raw=True, timeout=120))
                result[field].append(str(path))
    if not result['images']:
        raise ValueError('已完成任务没有图片输出，请检查 SaveImage 节点。')
    return result


def prepare(sequence: Path, out: Path) -> dict:
    manifest = json.loads((sequence / 'sequence.json').read_text('utf-8'))
    analysis = json.loads((sequence / 'reference_analysis.json').read_text('utf-8'))
    graph = json.loads((sequence / 'video/workflow.json').read_text('utf-8'))
    before = json.loads((sequence / 'video/result.json').read_text('utf-8'))
    if graph.get('8', {}).get('class_type') != 'WanAnimateToVideo':
        raise ValueError('对照样本必须是完整骨骼 Wan Animate 动画。')
    if not before.get('images') or not all(Path(p).is_file() for p in before['images']):
        raise ValueError('原始生成帧缺失，无法进行有效对照。')
    source = Path(manifest['reference'])
    if digest(source) != manifest['reference_sha256']:
        raise ValueError('参考图已经变化；请使用生成该动画时的原始图片。')
    out.mkdir(parents=True, exist_ok=True)
    report = prepare_generation_reference(source, out / 'source-input.png', analysis)
    with Image.open(analysis['opaque']) as image:
        old = np.array(image.convert('RGB')); image.convert('RGB').save(out / 'before-input.png')
    new = np.array(Image.open(report['path']).convert('RGB'))
    delta = np.abs(old.astype(np.int16) - new.astype(np.int16))
    report.update(
        before_input=str(analysis['opaque']), source_sha256=digest(source),
        before_input_sha256=digest(analysis['opaque']), after_input_sha256=digest(report['path']),
        input_changed_pixels=int(np.any(delta, axis=2).sum()),
        input_mean_absolute_channel_change=float(delta.mean()),
        input_max_channel_change=int(delta.max()),
    )
    experiment = {'schema_version': 1, 'status': 'prepared', 'baseline': str(sequence),
                  'baseline_prompt_id': before['prompt_id'], 'seed': graph['11']['inputs']['seed'],
                  'reference': report, 'controlled_parameters': 'all_nodes_except_LoadImage_7_image',
                  'warnings': ['单组固定种子对照不能证明通用准确率；需检查原始帧与透明帧。']}
    write_json(out / 'experiment.json', experiment)
    write_json(out / 'before-workflow.json', graph)
    return experiment


def review(sequence: Path, out: Path, experiment: dict, after: dict) -> None:
    repeated = out / 'baseline-repeat/video/result.json'
    before = json.loads((repeated if repeated.is_file() else sequence / 'video/result.json').read_text('utf-8'))
    experiment['baseline_repeated'] = repeated.is_file()
    experiment['compared_before_prompt_id'] = before['prompt_id']
    if len(before['images']) != len(after['images']):
        raise ValueError('对照两组生成帧数不同，不能比较。')
    raw_differences = []
    for index, (old_path, new_path) in enumerate(zip(before['images'], after['images'])):
        with Image.open(old_path) as image: old_rgb = np.array(image.convert('RGB'))
        with Image.open(new_path) as image: new_rgb = np.array(image.convert('RGB'))
        if old_rgb.shape != new_rgb.shape:
            raise ValueError('对照两组原始帧尺寸不同，不能比较。')
        delta = np.abs(old_rgb.astype(np.int16) - new_rgb.astype(np.int16))
        raw_differences.append({'frame': index, 'changed_pixels': int(np.any(delta, axis=2).sum()),
            'mean_absolute_channel_change': float(delta.mean()), 'max_channel_change': int(delta.max())})
    write_json(out / 'raw-differences.json', raw_differences)
    count = json.loads((sequence / 'sequence.json').read_text('utf-8'))['frame_count']
    indices = [round(i * (len(after['images']) - 1) / count) for i in range(count)]
    rows = []
    try:
        for group, result in (('before', before), ('after', after)):
            folder = out / group; folder.mkdir(exist_ok=True)
            for i, index in enumerate(indices):
                with Image.open(result['images'][index]) as raw:
                    rgba = raw.convert('RGBA'); matte = foreground_rgba(rgba, threading.Event(), anti_alias=False)
                unchanged = np.array_equal(np.array(rgba)[:, :, :3], np.array(matte)[:, :, :3])
                if not unchanged:
                    raise AssertionError('透明处理改变了生成 RGB，实验无效。')
                matte.save(folder / f'frame_{i:03d}.png')
                visible = np.array(matte)[:, :, 3] > 200
                rgb = np.array(matte)[:, :, :3]
                # A review statistic, not a claim that white pixels are defects.
                near_white = (rgb.min(axis=2) > 225) & (rgb.max(axis=2) - rgb.min(axis=2) < 20)
                rows.append({'group': group, 'frame': i, 'source_frame': index,
                             'rgb_preserved_by_matting': unchanged,
                             'visible_pixels': int(visible.sum()),
                             'near_white_fraction': float((near_white & visible).sum() / max(1, visible.sum()))})
                print(f'{group} matte {i+1}/{count}', flush=True)
    finally:
        release_session()
    # Compare the same four cycle phases. No image synthesis in this sheet.
    chosen = sorted(set([0, count // 4, count // 2, 3 * count // 4]))
    sheet = Image.new('RGB', (4 * 240, len(chosen) * 345 + 28), '#eeeeee')
    draw = ImageDraw.Draw(sheet)
    for column, label in enumerate(('BEFORE raw', 'AFTER raw', 'BEFORE final alpha', 'AFTER final alpha')):
        draw.text((column * 240 + 6, 6), label, fill='black')
    for row, i in enumerate(chosen):
        paths = [before['images'][indices[i]], after['images'][indices[i]],
                 out / 'before' / f'frame_{i:03d}.png', out / 'after' / f'frame_{i:03d}.png']
        for column, path in enumerate(paths):
            with Image.open(path) as image:
                image = image.convert('RGBA'); image.thumbnail((240, 320), Image.Resampling.NEAREST)
                tile = Image.new('RGBA', image.size, '#eeeeee'); tile.alpha_composite(image)
                sheet.paste(tile.convert('RGB'), (column * 240, 28 + row * 345))
            draw.text((column * 240 + 6, 350 + row * 345), f'frame {i+1}', fill='black')
    sheet.save(out / 'comparison.png')
    experiment.update(status='completed', after_prompt_id=after['prompt_id'], frames=rows,
                      comparison=str(out / 'comparison.png'),
                      raw_frame_count_per_group=len(after['images']), raw_frame_differences=raw_differences,
                      matting_model=MATTE_MODEL, matting_anti_alias=False,
                      interpretation='near_white_fraction 仅供人工定位色块，不代表缺色判定。')
    write_json(out / 'experiment.json', experiment)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sequence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8188')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--repeat-baseline', action='store_true', help='重新提交旧输入，使用已有 AFTER 结果完成严格对照')
    parser.add_argument('--resume', action='store_true', help='只恢复已完成任务的结果下载，不提交新生成')
    args = parser.parse_args()
    sequence, out = args.sequence.resolve(), args.out.resolve()
    experiment = (json.loads((out / 'experiment.json').read_text('utf-8'))
                  if args.repeat_baseline or args.resume else prepare(sequence, out))
    if not args.execute:
        print(json.dumps(experiment, ensure_ascii=False, indent=2)); return
    client = ComfyClient(args.url)
    run_out = out / 'baseline-repeat' if args.repeat_baseline else out
    if args.resume:
        prompt_id = json.loads((run_out / 'submitted.json').read_text('utf-8'))['prompt_id']
        result = download_completed(client, prompt_id, run_out / 'video')
        write_json(run_out / 'video/result.json', result)
        if args.repeat_baseline:
            result = json.loads((out / 'video/result.json').read_text('utf-8'))
        review(sequence, out, experiment, result)
        print('recovered without resubmitting', prompt_id, flush=True)
        return
    graph = json.loads((out / 'before-workflow.json').read_text('utf-8'))
    graph['7']['inputs']['image'] = client.upload_image(out / ('before-input.png' if args.repeat_baseline else 'source-input.png'))
    original = json.loads((out / 'before-workflow.json').read_text('utf-8'))
    comparison = deepcopy(graph); comparison['7']['inputs']['image'] = original['7']['inputs']['image']
    if comparison != original:
        raise AssertionError('对照工作流除了参考图输入还修改了其他参数。')
    (run_out / 'video').mkdir(parents=True, exist_ok=True)
    write_json(run_out / ('workflow.json' if args.repeat_baseline else 'after-workflow.json'), graph)
    started = time.monotonic()
    def emit(kind, data):
        if kind in ('queued', 'progress'):
            print(kind, data, flush=True)
    result = client.generate(graph, run_out / 'video', emit, threading.Event(), timeout=float('inf'),
                             submitted=lambda pid: write_json(run_out / 'submitted.json', {'prompt_id': pid}))
    write_json(run_out / 'video/result.json', result)
    timing = 'baseline_wait_and_download_seconds' if args.repeat_baseline else 'inference_wait_and_download_seconds'
    experiment[timing] = round(time.monotonic() - started, 3)
    if args.repeat_baseline:
        latest = json.loads((out / 'experiment.json').read_text('utf-8'))
        experiment = dict(latest, **{timing: experiment[timing]})
        result = json.loads((out / 'video/result.json').read_text('utf-8'))
    review(sequence, out, experiment, result)
    print('completed', str(out / 'experiment.json'), flush=True)


if __name__ == '__main__':
    main()
