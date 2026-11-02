"""Explicitly retire verified SDXL checkpoints, preserving all other model files.

The caller must supply exact paths and authorized checkpoint directories. No
directory enumeration/deletion, model inference, cancellation or restart occurs.
"""
import argparse
import json
from pathlib import Path
from typing import Callable

from aipictures.storage import write_json
from aipictures.workflow_library import digest

# Stability AI / RunDiffusion publisher LFS hashes, pinned in the research report.
ALLOWED = {
    'sd_xl_base_1.0_0.9vae.safetensors':
        (6938078334, 'e6bb9ea85bbf7bf6478a7c6d18b71246f22e95d41bcdd80ed40aa212c33cfeff'),
    'Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors':
        (7105348188, 'c9e3e68f89b8e38689e1097d4be4573cf308de4e3fd044c64ca697bdb4aa8bca'),
}


def remove(targets: list[Path], roots: list[Path], report: Path,
           before_delete: Callable[[], None]) -> dict:
    roots = [Path(root).absolute() for root in roots]
    for root in roots:
        if root.resolve(strict=True) != root:
            raise ValueError('检查点目录被重定向，请先检查实际路径。')
    scope = [str(root) for root in roots]
    result = (json.loads(report.read_text('utf-8')) if report.exists() else
              dict(scope=scope, deleted=[], skipped=[], reclaimed_bytes=0))
    if result['scope'] != scope:
        raise ValueError('报告属于其他目录，请换一个报告路径。')
    for target in dict.fromkeys(Path(p).absolute() for p in targets):
        if not any(target.is_relative_to(root) for root in roots):
            raise ValueError('目标不在明确授权的检查点目录：' + str(target))
        if target.name not in ALLOWED:
            raise ValueError('目标不在核验名单，保留：' + str(target))
        if not target.exists():
            continue
        if target.is_symlink() or target.resolve(strict=True) != target:
            result['skipped'].append(dict(path=str(target), reason='linked or redirected path'))
            continue
        size, checksum = ALLOWED[target.name]
        stat = target.stat()
        print('Verifying', target, flush=True)
        if stat.st_size != size or digest(target) != checksum:
            result['skipped'].append(dict(path=str(target), reason='size or publisher SHA mismatch'))
            continue
        before_delete()  # Shared queues may have changed while hashing.
        now = target.stat()
        if (target.resolve(strict=True) != target or
            (now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns) !=
            (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)):
            raise ValueError('核验期间目标发生变化，停止删除。')
        # Two existing checkpoint names may be hard links to ONE allocation.
        # Count reclaimed storage only when the final hard link is removed.
        freed = size if now.st_nlink == 1 else 0
        target.unlink()
        result['deleted'].append(dict(path=str(target), bytes=size, sha256=checksum,
                                      hard_links_before=now.st_nlink, reclaimed_bytes=freed))
        result['reclaimed_bytes'] += freed
        write_json(report, result)
    write_json(report, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, action='append', required=True)
    p.add_argument('--target', type=Path, action='append', required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--url', action='append', required=True)
    a = p.parse_args()
    from aipictures.engine import ComfyClient
    clients = [ComfyClient(url) for url in a.url]
    def idle():
        for client in clients:
            q = client.request('/queue')
            if q.get('queue_running') or q.get('queue_pending'):
                raise ValueError('共享后端有任务，停止删除；不会取消任何任务。')
    idle()
    for c in clients:
        c.request('/free', dict(unload_models=True, free_memory=True))
    result = remove(a.target, a.root, a.report, idle)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
