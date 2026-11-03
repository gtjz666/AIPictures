"""Install an isolated, pinned Windows multimodal runtime; never change ComfyUI."""
import argparse
import hashlib
import json
import re
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aipictures.storage import write_json

REPOSITORY = 'Qwen/Qwen3-VL-8B-Instruct-GGUF'
RUNTIME = 'b12064'
FILES = ('Qwen3VL-8B-Instruct-Q4_K_M.gguf', 'mmproj-Qwen3VL-8B-Instruct-F16.gguf')
MODEL_SCOPE = False


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        while block := source.read(8 * 1024**2):
            result.update(block)
    return result.hexdigest()


def download(url, target, size, expected):
    if url.startswith(('https://huggingface.co/', 'https://github.com/')):
        mirror = MODEL_SCOPE and url.startswith('https://huggingface.co/')
        if mirror:
            url = re.sub(r'/resolve/[^/]+/', '/resolve/master/', url.replace('https://huggingface.co/', 'https://modelscope.cn/models/'))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if mirror else (urllib.request._opener or urllib.request.build_opener())
        if target.exists():
            if target.stat().st_size == size and sha256(target) == expected:
                return
            raise ValueError('已有模型与发布记录不同，未覆盖。')
        target.parent.mkdir(parents=True, exist_ok=True)
        # Resolve once. Re-resolving every byte range hits hub request throttles;
        # the signed CDN URL supports independent ranges without new hub calls.
        with opener.open(urllib.request.Request(url, headers={'Range':'bytes=0-0'}), timeout=30) as response:
            content_url = response.url
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes 0-0/{size}':
                raise ValueError('下载源未提供有效字节范围，未安装。')
            response.read()
        jobs = [(target.with_name(target.name+f'.intent-download.part.range-{i}'), size*i//4, size*(i+1)//4-1) for i in range(4)]
        def part(job):
            file, begin, end = job
            while begin + (file.stat().st_size if file.exists() else 0) <= end:
                offset = begin + (file.stat().st_size if file.exists() else 0)
                stop = min(end, offset+8*1024**2-1)
                for attempt in range(10):
                    try:
                        def chunk(bounds):
                            a, b = bounds
                            req = urllib.request.Request(content_url, headers={'Range': f'bytes={a}-{b}'})
                            with opener.open(req, timeout=30) as response:
                                if response.status != 206 or response.headers.get('Content-Range') != f'bytes {a}-{b}/{size}':
                                    raise OSError('未返回请求的范围。')
                                data = response.read(b-a+1)
                                if len(data) != b-a+1:
                                    raise OSError('片段不完整。')
                                return data
                        ranges = [(a, min(stop, a+1024**2-1)) for a in range(offset, stop+1, 1024**2)]
                        with ThreadPoolExecutor(max_workers=8) as chunks:
                            data = b''.join(chunks.map(chunk, ranges))
                        with file.open('ab') as out:
                            out.write(data)
                        break
                    except (OSError, TimeoutError):
                        if attempt == 9: raise
                        time.sleep(min(attempt+1, 5))
                if (file.stat().st_size//(128*1024**2)) != ((file.stat().st_size-len(data))//(128*1024**2)):
                    print(f'{target.name}: range {begin} + {file.stat().st_size}', flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(part, jobs))
        merged = target.with_name(target.name+'.merged.intent-download.part')
        with merged.open('wb') as out:
            for file, _, _ in jobs:
                with file.open('rb') as source:
                    while block := source.read(8*1024**2): out.write(block)
        if merged.stat().st_size != size or sha256(merged) != expected:
            raise ValueError('模型发布SHA校验失败，未启用。')
        merged.rename(target)
        for file, _, _ in jobs: file.unlink()
        print('发布SHA校验通过：'+target.name, flush=True)
        return
    if target.exists():
        if target.stat().st_size == size and sha256(target) == expected:
            return
        raise ValueError('已有文件与发布校验不同，不覆盖：' + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.intent-download.part')
    for attempt in range(8):
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-'} if offset else {})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                append = offset and response.status == 206
                if append and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise ValueError('下载范围不符，保留临时文件。')
                with partial.open('ab' if append else 'wb') as output:
                    last = output.tell()
                    while block := response.read(4 * 1024**2):
                        output.write(block)
                        if output.tell() > size:
                            raise ValueError('下载大小超过发布记录。')
                        if output.tell() - last >= 128 * 1024**2:
                            print(f'{target.name}: {output.tell()}/{size}', flush=True)
                            last = output.tell()
            break
        except (OSError, TimeoutError) as exc:
            if attempt == 7:
                raise
            print(f'续传 {target.name}: {type(exc).__name__}', flush=True)
            time.sleep(min(2 ** attempt, 15))
    if partial.stat().st_size != size or sha256(partial) != expected:
        raise ValueError('下载校验失败，未启用：' + str(partial))
    partial.rename(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('D:/AIPicturesAssistant'))
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--proxy', help='Optional download proxy; never saved in application settings')
    parser.add_argument('--modelscope', action='store_true', help='Use Qwen ModelScope mirror, still require Hugging Face publisher SHA')
    args = parser.parse_args()
    global MODEL_SCOPE
    MODEL_SCOPE = args.modelscope
    if args.proxy:
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({'https': args.proxy})))
    root = args.root.resolve()
    info = get_json(f'https://huggingface.co/api/models/{REPOSITORY}')
    revision = info['sha']
    rows = get_json(f'https://huggingface.co/api/models/{REPOSITORY}/tree/{revision}')
    receipts = []
    for name in FILES:
        row = next(r for r in rows if r['path'] == name)
        target = root / 'models' / name
        download(f'https://huggingface.co/{REPOSITORY}/resolve/{revision}/{name}', target, row['size'], row['lfs']['oid'])
        receipts.append(dict(path=str(target), bytes=row['size'], sha256=row['lfs']['oid'], repository=REPOSITORY, revision=revision))
    release = get_json(f'https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{RUNTIME}')
    runtime = root / 'runtime' / RUNTIME
    for name in (f'llama-{RUNTIME}-bin-win-cuda-12.4-x64.zip', 'cudart-llama-bin-win-cuda-12.4-x64.zip'):
        asset = next(a for a in release['assets'] if a['name'] == name)
        expected = asset.get('digest', '').removeprefix('sha256:')
        if len(expected) != 64:
            raise ValueError('官方运行包缺少SHA256发布校验，未安装。')
        target = root / 'downloads' / name
        download(asset['browser_download_url'], target, asset['size'], expected)
        with zipfile.ZipFile(target) as archive:
            if any(not (runtime / n).resolve().is_relative_to(runtime.resolve()) for n in archive.namelist()):
                raise ValueError('运行包路径非法。')
            runtime.mkdir(parents=True, exist_ok=True)
            archive.extractall(runtime)
        receipts.append(dict(path=str(target), bytes=asset['size'], sha256=expected, url=asset['browser_download_url']))
    server = next(runtime.rglob('llama-server.exe'))
    config = dict(schema_version=1, name='Qwen3-VL-8B-Instruct Q4_K_M', server=str(server),
                  model=str(root/'models'/FILES[0]), projector=str(root/'models'/FILES[1]),
                  context=8192, max_tokens=1800, timeout=240, validated=False)
    write_json(root/'installation.json', dict(runtime=RUNTIME, files=receipts, settings=config))
    write_json(args.data/'local-intent-settings.json', config)
    print('下载并校验完成；需运行真实识别验收后启用。', flush=True)


if __name__ == '__main__':
    main()
