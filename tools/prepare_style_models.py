"""Install pinned public style LoRAs and the official image-restoration models."""
import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen

from aipictures.storage import DATA,write_json

UPSCALERS=[
    {'filename':'RealESRGAN_x2plus.pth','bytes':67061725,
     'url':'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth'},
    {'filename':'RealESRGAN_x4plus_anime_6B.pth','bytes':17938799,
     'url':'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth'},
]


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''): value.update(block)
    return value.hexdigest()


def install_file(target,spec):
    target=Path(target); expected=spec.get('sha256')
    if target.exists():
        checksum=digest(target)
        if target.stat().st_size!=spec['bytes'] or (expected and checksum!=expected):
            raise ValueError('已有文件不同，保留原文件：'+str(target))
        return {'path':str(target),'bytes':target.stat().st_size,'sha256':checksum,'source':spec['url']}
    target.parent.mkdir(parents=True,exist_ok=True)
    partial=target.with_name(target.name+'.style-download.part')
    for attempt in range(6):
        offset=partial.stat().st_size if partial.exists() else 0
        if offset==spec['bytes']: break
        try:
            separator='&' if '?' in spec['url'] else '?'
            url=spec['url']+separator+f'download=true&resume={offset}&ts={int(time.time())}'
            with urlopen(Request(url,headers={'Range':f'bytes={offset}-'} if offset else {}),timeout=45) as response:
                if offset and (response.status!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {offset}-')):
                    raise ValueError('服务器不支持本次续传，保留部分文件。')
                with partial.open('ab' if offset else 'wb') as stream:
                    for block in iter(lambda:response.read(4*1024*1024),b''): stream.write(block)
            break
        except Exception:
            if attempt==5: raise
            time.sleep(min(3*(attempt+1),15))
    checksum=digest(partial)
    if partial.stat().st_size!=spec['bytes'] or (expected and checksum!=expected):
        raise ValueError('下载完整性检查失败，未安装：'+str(target))
    os.rename(partial,target)
    print('Installed:',target.name,flush=True)
    return {'path':str(target),'bytes':target.stat().st_size,'sha256':checksum,'source':spec['url'],
        'publisher_sha256_verified':bool(expected)}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--models',required=True)
    args=parser.parse_args(); root=Path(args.models).resolve()
    catalog=json.loads((Path(__file__).resolve().parents[1]/'aipictures/resources/lora_catalog.json').read_text('utf-8'))
    jobs=[(root/'loras'/item['filename'],item['download']) for item in catalog['models']]
    jobs += [(root/'upscale_models'/item['filename'],item) for item in UPSCALERS]
    with ThreadPoolExecutor(max_workers=3) as pool:
        records=list(pool.map(lambda job:install_file(*job),jobs))
    write_json(DATA/'style-model-installation.json',{'installed':True,'files':records,'bytes':sum(r['bytes'] for r in records)})
    print('Style models installed:',len(records),flush=True)


if __name__=='__main__': main()
