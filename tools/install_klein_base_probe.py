"""Pinned official Base FP8 download for an isolated comparison; never registers a default."""
import hashlib,time
from pathlib import Path
import httpx
from aipictures.storage import write_json

REPO='black-forest-labs/FLUX.2-klein-base-4b-fp8'
REVISION='103db268c10d4d3921101b46057671f9ac460da6'
NAME='flux-2-klein-base-4b-fp8.safetensors'
SIZE=4089498488
SHA='44bab3a86fe98b85d21dd2a4729ebdc3ae51fb8a39f76e457e18c724219e6840'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
    return h.hexdigest()


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--models',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);args=p.parse_args()
    target=args.models/NAME;partial=target.with_suffix('.safetensors.partial')
    args.models.mkdir(parents=True,exist_ok=True)
    with httpx.Client(follow_redirects=True,timeout=httpx.Timeout(60,connect=30)) as c:
        if not target.exists():
            if partial.exists():raise ValueError('Existing partial download requires inspection before resuming')
            last=time.monotonic();count=0
            with c.stream('GET',f'https://huggingface.co/{REPO}/resolve/{REVISION}/{NAME}') as r:
                r.raise_for_status()
                with partial.open('xb') as out:
                    for chunk in r.iter_bytes(1024**2):
                        out.write(chunk);count+=len(chunk)
                        if time.monotonic()-last>20:print(f'Downloaded {count/1024**3:.2f} / {SIZE/1024**3:.2f} GiB',flush=True);last=time.monotonic()
            if partial.stat().st_size!=SIZE or digest(partial)!=SHA:raise ValueError('Downloaded Base checksum mismatch')
            partial.rename(target)
        if target.stat().st_size!=SIZE or digest(target)!=SHA:raise ValueError('Installed Base checksum mismatch')
        url='https://huggingface.co/thedeoxen/refcontrol-FLUX.2-klein-4B-reference-depth-lora/resolve/0ae1ef7f9acc4e55ec2237360943c3c3032d3583/image_flux2_klein_image_edit_4b_refcontrol_depth.json'
        response=c.get(url);response.raise_for_status();workflow=response.json()
        nodes={n['type']:n for n in workflow['nodes'] if n['type'] in ('UNETLoader','Flux2Scheduler','CFGGuider')}
        write_json(args.receipt.with_name('author-workflow.json'),workflow)
        write_json(args.receipt,dict(repository=REPO,revision=REVISION,file=str(target.resolve()),bytes=SIZE,sha256=SHA,
            author_workflow_url=url,author_steps=nodes['Flux2Scheduler']['widgets_values'][0],author_cfg=nodes['CFGGuider']['widgets_values'][0],default_changed=False,environment_changed=False))
    print('Verified official Base FP8; default unchanged',flush=True)


if __name__=='__main__':main()
