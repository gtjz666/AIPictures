"""Recover a saved animation latent after a backend exit, without resampling."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import threading
import time

from aipictures.animation_decode import decode_sampled
from aipictures.backend_connection import shared_backend_url
from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.pose_animation import export_frames
from aipictures.storage import write_json
from aipictures.workflow_library import digest
from tools.verify_animation_modes import inspect_exports


def saved_sampling(sequence: Path) -> tuple[dict, dict]:
    """Read the existing sample and reject changed or missing source data."""
    manifest = json.loads((sequence / 'sequence.json').read_text('utf-8'))
    if manifest.get('status') == 'completed' or manifest.get('frames'):
        raise ValueError('序列已有导出帧，请使用新目录，不能覆盖已生成素材。')
    sampled = json.loads((sequence / 'video/sampling_result.json').read_text('utf-8'))
    if sampled['prompt_id'] != manifest.get('sampling_prompt_id'):
        raise ValueError('采样任务编号不匹配，不能恢复。')
    paths = sampled.get('latents', [])
    if len(paths) != 1:
        raise ValueError('需要唯一的已保存采样文件，不能重新生成代替。')
    latent = Path(paths[0])
    if not latent.is_file():
        latent = sequence / 'video' / latent.name
    if not latent.is_file():
        raise ValueError('采样文件缺失，请恢复原始 .latent 文件。')
    source = sequence / 'video/decode/source.json'
    if source.is_file():
        expected = json.loads(source.read_text('utf-8')).get('latent_sha256')
        if expected and digest(latent) != expected:
            raise ValueError('采样文件校验不一致，不能恢复。')
    sampled['latents'] = [str(latent.resolve())]
    return manifest, sampled


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sequence', type=Path, required=True)
    parser.add_argument('--decode-dir', type=Path, required=True,
                        help='新的解码输出目录；失败记录保留。')
    parser.add_argument('--url', default='http://127.0.0.1:8188')
    parser.add_argument('--resume-decode', action='store_true',
                        help='仅恢复此目录已有任务，不提交新任务。')
    args = parser.parse_args()
    sequence = args.sequence.resolve()
    manifest, sampled = saved_sampling(sequence)
    client = ComfyClient(shared_backend_url(args.url))
    cancel = threading.Event()
    started = time.monotonic()

    def emit(kind: str, data: dict) -> None:
        print(json.dumps({'kind': kind, 'data': data}, ensure_ascii=True), flush=True)

    if args.resume_decode:
        graph = json.loads((args.decode_dir / 'workflow.json').read_text('utf-8'))
        pid = json.loads((args.decode_dir / 'submitted.json').read_text('utf-8'))['prompt_id']
        result = client.resume(pid, graph, args.decode_dir, emit, cancel)
        result.update(latents=sampled['latents'], sampling_prompt_id=sampled['prompt_id'],
                      decode_prompt_id=pid, image_workflow=str(args.decode_dir / 'workflow.json'))
    else:
        if args.decode_dir.exists():
            parser.error('解码目录已存在。请用 --resume-decode 恢复原任务，或选择新的目录。')
        queue = client.request('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            parser.error('共享后端有任务，请完成后再恢复，不会中断现有任务。')
        result = decode_sampled(client, sampled, args.decode_dir, emit, cancel)
    if len(result['images']) != manifest['source_frame_count']:
        raise ValueError('解码帧数与原采样记录不一致，原始数据保留。')
    write_json(args.decode_dir / 'result.json', result)
    write_json(sequence / 'video/result.json', result)
    backup = sequence / 'sequence-before-recovery.json'
    if not backup.exists():
        write_json(backup, deepcopy(manifest))
    manifest.pop('error', None)
    manifest.update(status='exporting', prompt_id=result['prompt_id'],
                    decode_prompt_id=result['decode_prompt_id'],
                    workflow_stages={'sampling': str(sequence / 'video/workflow.json'),
                                     'decode': result['image_workflow']},
                    recovery={'resampled': False, 'sampling_prompt_id': sampled['prompt_id'],
                              'latent_sha256': digest(sampled['latents'][0]),
                              'failed_decode_record': str(sequence / 'video/decode'),
                              'recovered_decode_record': str(args.decode_dir)})
    timings = manifest['timings']
    monitor = json.loads((sequence / 'video/monitor.json').read_text('utf-8'))
    timings['sampling_wait_and_download_seconds'] = monitor['elapsed_seconds']
    timings['decode_recovery_seconds'] = round(time.monotonic() - started, 3)
    manifest['video_cache_release'] = release_idle_models(client)
    clip = json.loads((sequence / 'motion.json').read_text('utf-8'))
    export_frames(sequence, result, manifest, clip, emit, cancel)
    timings['recovery_and_export_seconds'] = round(time.monotonic() - started, 3)
    manifest['final_cache_release'] = release_idle_models(client)
    write_json(sequence / 'sequence.json', manifest)
    record = inspect_exports(sequence)
    write_json(sequence / 'acceptance.json', record)
    print(json.dumps(record, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
