"""Install only two pinned structure-control components; no environment changes."""
import argparse,hashlib,json,os,shutil
from pathlib import Path
import httpx

ROOT=Path('D:/ComfyModels/structure-control')
FILES=[('thedeoxen/refcontrol-FLUX.2-klein-4B-reference-depth-lora','0ae1ef7f9acc4e55ec2237360943c3c3032d3583','flux2_klein_4b_refcontrol_depth.safetensors',92426784,'65ec4c71fa7538b2201481928609a5836773f0dc06a4041b2d28abd05826c401'),
       ('depth-anything/Depth-Anything-V2-Small','03876f8651c73a60fe4c2c48294e09fcb6838fcf','depth_anything_v2_vits.pth',99218434,'715fade13be8f229f8a70cc02066f656f2423a59effd0579197bbf57860e1378')]

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--loras',type=Path,default=Path(os.environ['LOCALAPPDATA'])/'Comfy-Desktop/ComfyUI-Shared/models/loras')
    args=p.parse_args();root=args.root;root.mkdir(parents=True,exist_ok=True);records=[]
    with httpx.Client(follow_redirects=True,timeout=120) as client:
        for repo,revision,name,size,sha in FILES:
            target=root/name
            if not target.exists():
                partial=target.with_suffix(target.suffix+'.partial')
                if partial.exists():raise ValueError('Existing partial download requires inspection: '+str(partial))
                with client.stream('GET',f'https://huggingface.co/{repo}/resolve/{revision}/{name}') as response:
                    response.raise_for_status()
                    with partial.open('xb') as out:
                        for data in response.iter_bytes(1024**2):out.write(data)
                if partial.stat().st_size!=size or digest(partial)!=sha:raise ValueError('Downloaded model checksum mismatch: '+name)
                partial.rename(target)
            if target.stat().st_size!=size or digest(target)!=sha:raise ValueError('Installed model checksum mismatch: '+name)
            records.append(dict(repository=repo,revision=revision,path=str(target),bytes=size,sha256=sha))
            print('Verified '+name,flush=True)
    lora=args.loras/FILES[0][2]
    lora.parent.mkdir(parents=True,exist_ok=True)
    if not lora.exists():
        try:os.link(root/FILES[0][2],lora)
        except OSError as exc:
            if getattr(exc,'winerror',None)!=17:raise
            shutil.copyfile(root/FILES[0][2],lora)
    if digest(lora)!=FILES[0][4]:raise ValueError('Shared adapter checksum mismatch')
    (root/'installation.json').write_text(json.dumps(dict(files=records,lora_link=str(lora),environment_changed=False),indent=2),encoding='utf-8')

if __name__=='__main__':main()
