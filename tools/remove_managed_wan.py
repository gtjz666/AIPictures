"""Retire only publisher-identical Wan weights with AIPictures install receipts.

Never glob-delete model folders. Original ControlNet, pose detection, CLIP Vision
and the user's workflows are outside this allowlist and remain untouched.
"""
import argparse
import json
from pathlib import Path
from typing import Callable

from aipictures.storage import write_json
from aipictures.workflow_library import digest

# Publisher LFS hashes, Comfy-Org/Wan-2.2 revision ee6f4a40737a995bf5818954cfce6d59443b0f04,
# plus the pinned Kijai Animate revision already recorded by the original installer.
ALLOWED = {
    'diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors':
        (14294742832, '6122e79d55e0f235698d11d657f3b196c5273c830da00b2b013c5a048d5e6a42'),
    'diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors':
        (14294742832, '5471a457b6ac404202a5fbe6c11595a3d5641fc766b00f38763f72303fffc21e'),
    'text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors':
        (6735906897, 'c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68'),
    'vae/wan_2.1_vae.safetensors':
        (253815318, '2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148962b'),
    'diffusion_models/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors':
        (18401760586, '2936b31473a967e7a429a6646bba60e7862d0938e178b58b2a140f391dd5b8e6'),
}


def remove(receipts: list[Path], model_root: Path, report: Path,
           before_delete: Callable[[], None]) -> dict:
    root = Path(model_root).resolve(strict=True)
    if Path(report).exists():
        result = json.loads(Path(report).read_text('utf-8'))
        if result.get('scope') != str(root):
            raise ValueError('删除收据的目标目录不同，请换一个报告路径。')
    else:
        result = {'scope': str(root), 'deleted': [], 'skipped': [], 'reclaimed_bytes': 0}
    seen = set()
    for receipt in receipts:
        data = json.loads(Path(receipt).read_text('utf-8'))
        for row in data.get('files', []):
            path = Path(row['path']) if row.get('path') else Path(data.get('models_root', root)) / row['relative_path']
            # Check the absolute lexical target AND resolved target: a junction must
            # not make an outside path appear to be a managed weight or vice versa.
            absolute = path.absolute()
            if not absolute.is_relative_to(root):
                continue
            relative = absolute.relative_to(root).as_posix()
            if relative not in ALLOWED or relative in seen:
                continue
            seen.add(relative)
            size, checksum = ALLOWED[relative]
            verified = row.get('sha256') == checksum or row.get('installer_sha256_verified') is True
            if row.get('bytes') != size or not verified:
                result['skipped'].append({'path': str(path), 'reason': 'installation receipt mismatch'})
                continue
            if not path.exists():
                continue
            resolved = path.resolve(strict=True)
            if path.is_symlink() or resolved != absolute or not resolved.is_relative_to(root):
                result['skipped'].append({'path': str(path), 'reason': 'linked or redirected path preserved'})
                continue
            print('Verifying', relative, flush=True)
            before = path.stat()
            if before.st_size != size or digest(path) != checksum:
                result['skipped'].append({'path': str(path), 'reason': 'changed file preserved'})
                continue
            # Queue may have changed while reading a large file. Recheck directly
            # before this individual unlink; never interrupt an active user task.
            before_delete()
            after = path.stat()
            if path.resolve(strict=True) != resolved or (after.st_size, after.st_mtime_ns, after.st_ino) != (before.st_size, before.st_mtime_ns, before.st_ino):
                raise ValueError('核验期间模型路径或文件发生变化，已停止。')
            path.unlink()
            result['deleted'].append({'path': str(resolved), 'bytes': size, 'sha256': checksum})
            result['reclaimed_bytes'] += size
            write_json(report, result)
    write_json(report, result)
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--models', type=Path, required=True)
    p.add_argument('--receipt', type=Path, action='append', required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--url', action='append', help='All running ComfyUI instances sharing these model files.')
    a = p.parse_args()
    from aipictures.engine import ComfyClient, EngineUnavailable
    clients = [ComfyClient(url) for url in (a.url or ['http://127.0.0.1:8188'])]
    def idle() -> None:
        try:
            for client in clients:
                queue = client.request('/queue')
                if queue.get('queue_running') or queue.get('queue_pending'):
                    raise ValueError('ComfyUI有任务，停止删除模型；不会取消其他任务。')
        except EngineUnavailable:
            raise ValueError('无法核对共享后端队列，本次保留权重。') from None
    idle()
    for client in clients:
        client.request('/free', {'unload_models': True, 'free_memory': True})
    result = remove(a.receipt, a.models, a.report, idle)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
