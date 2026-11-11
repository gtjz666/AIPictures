"""Install only Sony's text-to-SFX assets; verify published release digests."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from concurrent.futures import ThreadPoolExecutor
import requests


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--proxy');args=parser.parse_args()
    root=args.root.resolve();release=json.loads((root/'release.json').read_text('utf-8'))
    installed=root/'installation.json'
    if installed.is_file():
        files=json.loads(installed.read_text('utf-8')).get('files',[])
        if files and all(Path(row['path']).is_file() and Path(row['path']).stat().st_size==row['bytes'] and sha(Path(row['path']))==row['sha256'] for row in files):
            print('Installed weights match their receipt; no duplicate download',flush=True);return
    def install(name):
        asset=next(a for a in release['assets'] if a['name']==name)
        target=root/'downloads'/name;target.parent.mkdir(exist_ok=True)
        expected=asset['digest'].removeprefix('sha256:')
        if not target.exists():
            partial=target.with_suffix('.partial')
            while (partial.stat().st_size if partial.exists() else 0)<asset['size']:
                start=partial.stat().st_size if partial.exists() else 0
                end=min(asset['size']-1,start+32*1024*1024-1)
                with requests.get(asset['browser_download_url'],headers={'Range':f'bytes={start}-{end}'},stream=True,timeout=(30,30),proxies={'https':args.proxy} if args.proxy else None) as response:
                    response.raise_for_status()
                    if response.status_code!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {start}-'):raise ValueError('Server did not honor range; partial preserved')
                    with partial.open('ab') as f:
                        for chunk in response.iter_content(1024*1024):f.write(chunk);f.flush()
                print(f'{name}: {partial.stat().st_size}/{asset["size"]}',flush=True)
            if partial.stat().st_size!=asset['size'] or sha(partial)!=expected:raise ValueError('Release digest mismatch: '+name)
            partial.rename(target)
        if target.stat().st_size!=asset['size'] or sha(target)!=expected:raise ValueError('Existing release digest mismatch: '+name)
        destination=root/'source'
        with zipfile.ZipFile(target) as z:
            for member in z.infolist():
                resolved=(destination/member.filename).resolve()
                if not resolved.is_relative_to(destination.resolve()):raise ValueError('Unsafe archive path')
            z.extractall(destination)
        receipt=dict(asset=name,bytes=asset['size'],sha256=expected)
        print(json.dumps(receipt),flush=True);return receipt
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts=list(pool.map(install,('TextConditionerA.zip','Woosh-AE.zip','Woosh-Flow.zip')))
    (root/'download-receipt.json').write_text(json.dumps(dict(release=release['html_url'],assets=receipts),indent=2),'utf-8')


if __name__=='__main__':main()
