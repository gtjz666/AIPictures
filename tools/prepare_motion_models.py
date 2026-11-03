"""Bounded parallel range downloads, pinned publisher SHA; no overwrite of changed models."""
import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,ProxyHandler,build_opener

from aipictures.storage import write_json


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def download(target,spec,opener):
    if target.exists():
        if target.stat().st_size!=spec['bytes'] or sha(target)!=spec['sha256']:raise ValueError('已有模型不同，保留：'+str(target))
        return dict(path=str(target),**spec,publisher_sha256_verified=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    partial=target.with_name(target.name+'.style-download.part')
    offset=partial.stat().st_size if partial.exists() else 0
    if offset>spec['bytes']:raise ValueError('部分文件超过预期大小，保留供检查。')
    jobs=[];remaining=spec['bytes']-offset
    for i in range(4):
        begin=offset+remaining*i//4;end=offset+remaining*(i+1)//4-1
        if begin<=end:jobs.append((partial.with_name(partial.name+f'.range-{begin}-{end}'),begin,end))
    def part(job):
        path,begin,end=job;wanted=end-begin+1
        for attempt in range(6):
            received=path.stat().st_size if path.exists() else 0
            if received==wanted:return
            if received>wanted:raise ValueError('下载片段过大，保留。')
            start=begin+received
            try:
                url=spec['url']+f'?download=true&segment={start}&ts={time.time_ns()}'
                with opener.open(Request(url,headers={'Range':f'bytes={start}-{end}'}),timeout=50) as r:
                    if r.status!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{spec["bytes"]}':
                        raise ValueError('服务器未按请求返回字节范围，停止以保护已下载数据。')
                    with path.open('ab') as f:
                        for block in iter(lambda:r.read1(64*1024),b''):f.write(block)
                if path.stat().st_size!=wanted:raise OSError('下载提前结束，续传原片段。')
                return
            except (OSError,TimeoutError):
                if attempt==5:raise
                time.sleep(min(3+attempt*2,12))
        raise ValueError('片段下载未完成。')
    print('RESUMING',target.name,offset,spec['bytes'],flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(part,jobs))
    if (partial.stat().st_size if partial.exists() else 0)!=offset:raise ValueError('部分文件被其他下载任务修改，停止合并。')
    with partial.open('ab') as out:
        for path,_,_ in jobs:
            with path.open('rb') as src:
                for block in iter(lambda:src.read(8*1024*1024),b''):out.write(block)
    if partial.stat().st_size!=spec['bytes'] or sha(partial)!=spec['sha256']:raise ValueError('发布SHA核验失败，未安装。')
    partial.rename(target)
    for path,_,_ in jobs:
        if not path.resolve().is_relative_to(target.parent.resolve()):raise ValueError('临时片段路径异常，保留。')
        path.unlink()
    print('PUBLISHER_SHA_VERIFIED',target.name,flush=True)
    return dict(path=str(target),**spec,publisher_sha256_verified=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--metadata',type=Path,default=Path(__file__).with_name('motion_models.json'));p.add_argument('--models',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True);p.add_argument('--proxy');p.add_argument('--audio',action='store_true')
    a=p.parse_args();meta=json.loads(a.metadata.read_text('utf-8'))
    opener=build_opener(ProxyHandler({'https':a.proxy,'http':a.proxy}) if a.proxy else ProxyHandler({}))
    records=[]
    for row in meta['files']:
        if row['path'].endswith('pruned_w6a8.safetensors'):continue
        if not a.audio and row['path'].endswith('minimax_h3_audio_vae_fp32.safetensors'):continue
        spec=dict(bytes=row['size'],sha256=row['lfs']['oid'],url=f"https://huggingface.co/{meta['repo']}/resolve/{meta['revision']}/{row['path']}")
        records.append(download(a.models/row['path'],spec,opener))
        write_json(a.receipt,dict(repo=meta['repo'],revision=meta['revision'],files=records))
    print('NATIVE_REFERENCE_MODELS_COMPLETE',sum(r['bytes'] for r in records),flush=True)


if __name__=='__main__':main()
