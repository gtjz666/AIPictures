"""Download only explicitly requested Wan weights; pin revision, verify SHA-256, preserve existing files."""
import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

REPO = 'Comfy-Org/Wan-2.2'
FILES = {
    '5b': ['diffusion_models/wan2.2_ti2v_5B_fp16.safetensors', 'vae/wan2.2_vae.safetensors'],
    '14b': ['diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors',
            'diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors', 'vae/wan_2.1_vae.safetensors'],
}
TEXT_ENCODER = 'text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors'


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''): value.update(chunk)
    return value.hexdigest()


def read_metadata(url):
    for attempt in range(6):
        try: return json.load(urlopen(url,timeout=30))
        except Exception:
            if attempt == 5: raise
            time.sleep(2 * (attempt + 1))


def install(models, variant, download=False, workers=3):
    models = Path(models).resolve()
    metadata = read_metadata(f'https://huggingface.co/api/models/{REPO}')
    revision = metadata['sha']
    def install_one(relative):
        directory, filename = relative.split('/')
        entries = read_metadata(f'https://huggingface.co/api/models/{REPO}/tree/{revision}/split_files/{directory}')
        entry = next(item for item in entries if item['path'] == 'split_files/' + relative)
        size, checksum = entry['size'], entry['lfs']['oid']
        target = models / relative
        print(f'{filename}: {size / 1e9:.2f} GB, SHA256 {checksum}', flush=True)
        if not download: return None
        if target.exists():
            if target.stat().st_size != size or sha256(target) != checksum:
                raise ValueError('Existing model differs; left untouched: ' + str(target))
            print('Verified existing file.', flush=True); return str(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + '.wan-download.part')
        url = f'https://huggingface.co/{REPO}/resolve/{revision}/split_files/{relative}'
        attempts = 0
        while not partial.exists() or partial.stat().st_size < size:
            offset = partial.stat().st_size if partial.exists() else 0
            try:
                request = Request(url + (f'?download=true&resume={offset}' if offset else ''),
                                  headers={'Range': f'bytes={offset}-'} if offset else {})
                with urlopen(request, timeout=45) as response:
                    append = offset > 0 and response.status == 206
                    if offset and (not append or not response.headers.get('Content-Range','').startswith(f'bytes {offset}-')):
                        raise RuntimeError('Server did not honor resume offset; existing partial file preserved.')
                    if not append: offset = 0
                    with partial.open('ab' if append else 'wb') as stream:
                        reported = offset
                        for chunk in iter(lambda: response.read(8 * 1024 * 1024), b''):
                            stream.write(chunk); offset += len(chunk)
                            if offset - reported >= 256 * 1024 * 1024:
                                print(f'{filename}: {offset / size:.1%} ({offset / 1e9:.2f} GB)', flush=True); reported = offset
                attempts = 0
            except Exception as exc:
                attempts += 1
                print(f'Download interrupted ({type(exc).__name__}); resume attempt {attempts}/8.', flush=True)
                if attempts >= 8: raise RuntimeError('Download failed; partial file retained for resume.') from None
                time.sleep(min(5 * attempts, 30))
        if partial.stat().st_size != size or sha256(partial) != checksum:
            raise ValueError('Downloaded file failed verification; not installed: ' + str(partial))
        # On Windows rename refuses to overwrite an existing destination, including a concurrent install.
        os.rename(partial, target)
        print('Verified and installed: ' + str(target), flush=True); return str(target)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [value for value in pool.map(install_one, FILES[variant] + [TEXT_ENCODER]) if value]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', required=True); parser.add_argument('--variant', choices=FILES, default='14b')
    parser.add_argument('--download', action='store_true', help='Only use after the user approves these weights.')
    parser.add_argument('--workers', type=int, choices=(1,2,3,4), default=3)
    args = parser.parse_args(); install(args.models, args.variant, args.download, args.workers)
