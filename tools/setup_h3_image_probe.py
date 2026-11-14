"""Pinned, isolated H3-Image research setup. Never registers a production engine."""
import argparse,hashlib,json,os,shutil,subprocess,time,zipfile
from pathlib import Path
import httpx

SOURCE='c1eece62cbf1805d4f64286d7f5592e6a215e6ba'
MODEL_REV='0bb149f51e3156ed4b90dd45d5620346bfe1df8f'
ENCODER_SIZE=15687142551
ENCODER_SHA='35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6'
FILES=[('diffusion_models/minimax_h3_image_pruned_w4a8.safetensors',12549794530,'517cc19b85348386f4df7c806dce80d839d0899e7cdaa3e1dbb09de964381dbb'),
       ('vae/minimax_h3_image_vae_fp16.safetensors',1168505312,'d80e9c2e5cfc9844869961ff5a58c9a9e52182df6bfb30b26018dd7f348721af')]

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024**2),b''):h.update(block)
    return h.hexdigest()

def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--models',type=Path,required=True)
    p.add_argument('--borrow-python',type=Path,required=True);p.add_argument('--encoder',type=Path,required=True)
    p.add_argument('--proxy');p.add_argument('--resume-downloads',action='store_true');a=p.parse_args()
    root=a.root.resolve();models=a.models.resolve();encoder=a.encoder.resolve()
    if not encoder.is_file() or not a.borrow_python.is_file():raise ValueError('Existing runtime/encoder missing')
    if encoder.stat().st_size!=ENCODER_SIZE or sha(encoder)!=ENCODER_SHA:raise ValueError('Existing H3 encoder publisher checksum mismatch')
    records=[dict(path=str(models/name),bytes=size,sha256=digest,url=f'https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/{MODEL_REV}/{name}') for name,size,digest in FILES]
    with httpx.Client(proxy=a.proxy,follow_redirects=True,timeout=120) as client:
        if a.resume_downloads:
            config=json.loads((root/'machine.json').read_text('utf-8'))
            if config['source_commit']!=SOURCE or config['models']!=records:raise ValueError('Resume specification changed')
        else:
            root.mkdir(parents=True,exist_ok=False);source=root/'ComfyUI';source.mkdir()
            archive=root/'source.zip'
            with client.stream('GET',f'https://codeload.github.com/Comfy-Org/ComfyUI/zip/{SOURCE}') as response:
                response.raise_for_status()
                with archive.open('xb') as f:
                    for b in response.iter_bytes(1024**2):f.write(b)
            with zipfile.ZipFile(archive) as z:
                for member in z.infolist():
                    parts=Path(member.filename).parts
                    if len(parts)<2:continue
                    target=(source/Path(*parts[1:])).resolve()
                    if not target.is_relative_to(source) or (member.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe archive path')
                    if member.is_dir():target.mkdir(parents=True,exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True,exist_ok=True)
                        with z.open(member) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
            env=root/'env';subprocess.run([str(a.borrow_python),'-m','venv',str(env)],check=True)
            site=a.borrow_python.resolve().parents[1]/'Lib/site-packages'
            (env/'Lib/site-packages/borrowed_h3.pth').write_text('import site; site.addsitedir('+repr(str(site))+')\n','utf-8')
            # Only this new environment receives the kernel update. Torch remains read-only.
            command=[str(env/'Scripts/python.exe'),'-m','pip','install','--no-deps','comfy-kitchen==0.2.41']
            if a.proxy:command+=['--proxy',a.proxy]
            subprocess.run(command,check=True)
            repo=Path(__file__).resolve().parents[1];nodes=source/'custom_nodes/aipictures_image_probe';nodes.mkdir()
            for name in ('stream_weights.py','conditioning.py'):shutil.copy2(repo/'comfy_nodes/aipictures_motion'/name,nodes/name)
            (nodes/'__init__.py').write_text('from .stream_weights import install_stream_loader\ninstall_stream_loader()\nfrom .conditioning import SaveConditioning,LoadConditioning\nNODE_CLASS_MAPPINGS={"AIPicturesSaveConditioning":SaveConditioning,"AIPicturesLoadConditioning":LoadConditioning}\n','utf-8')
            paths=root/'model-paths.yaml'
            save(paths,dict(image_probe=dict(base_path=models.as_posix(),diffusion_models='diffusion_models',vae='vae'),existing_encoder=dict(text_encoders=encoder.parent.as_posix())))
            config=dict(validated=False,python=str(env/'Scripts/python.exe'),source=str(source),source_commit=SOURCE,
                source_archive_sha256=sha(archive),model_revision=MODEL_REV,model_paths=str(paths),models=records,
                encoder=dict(path=str(encoder),bytes=encoder.stat().st_size,sha256=ENCODER_SHA),production_settings_changed=False,
                copied_nodes_sha256={str(f.relative_to(nodes)):sha(f) for f in nodes.glob('*.py')})
            save(root/'machine.json',config)
        for row in records:
            target=Path(row['path']);target.parent.mkdir(parents=True,exist_ok=True);partial=target.with_suffix('.safetensors.partial')
            if target.exists():
                if target.stat().st_size!=row['bytes'] or sha(target)!=row['sha256']:raise ValueError('Existing model mismatch')
                print('Already verified '+target.name,flush=True);continue
            start=partial.stat().st_size if partial.exists() else 0
            if start and not a.resume_downloads:raise ValueError('Inspect partial then explicitly resume downloads')
            if start>row['bytes'] or shutil.disk_usage(models).free<row['bytes']-start+4*1024**3:raise ValueError('Insufficient free disk or invalid partial')
            if start<row['bytes']:
                headers={'Range':f'bytes={start}-'} if start else {};last=0
                with client.stream('GET',row['url'],headers=headers) as response:
                    response.raise_for_status()
                    if start and (response.status_code!=206 or not response.headers.get('content-range','').startswith(f'bytes {start}-')):raise ValueError('Range not honored')
                    with partial.open('ab' if start else 'xb') as f:
                        for block in response.iter_bytes(4*1024**2):
                            f.write(block);start+=len(block)
                            if time.monotonic()-last>10:
                                print(f'{target.name}: {start/row["bytes"]:.1%}',flush=True)
                                save(root/'download-progress.json',dict(file=target.name,received=start,total=row['bytes']));last=time.monotonic()
            if partial.stat().st_size!=row['bytes'] or sha(partial)!=row['sha256']:raise ValueError('Downloaded model checksum mismatch')
            partial.rename(target);print('Verified '+target.name,flush=True)
        save(root/'installation.json',dict(files=records,models_sha256_verified=True,new_bytes=sum(r['bytes'] for r in records),production_settings_changed=False))
        print('Isolated image probe ready; not registered or quality-validated.',flush=True)

if __name__=='__main__':main()
