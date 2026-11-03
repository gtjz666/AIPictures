"""Optional isolated native Comfy setup. Never upgrade the original Comfy/H3 environments."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.request import ProxyHandler,build_opener
from aipictures.storage import write_json

REVISION='bb878b9ee35274e67931634ba9e8c338f8c06035'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True,help='New private directory; existing directories are not overwritten')
    p.add_argument('--h3-root',type=Path,required=True,help='Existing, verified H3 installation with unified Python 3.12/CUDA13 runtime')
    p.add_argument('--models',type=Path,required=True);p.add_argument('--proxy')
    a=p.parse_args();root=a.root.resolve();h3=a.h3_root.resolve()
    runtime=h3/'envs/unified';python=runtime/'Scripts/python.exe';site=runtime/'Lib/site-packages'
    if not python.is_file() or not site.is_dir():raise ValueError('找不到已有H3独立运行时；先按VIDEO_FIRST安装/验证H3。')
    subprocess.run([str(python),'-c',"import sys;from importlib.metadata import version;assert sys.version_info[:2]==(3,12);assert '+cu130' in version('torch')"],check=True)
    if root.exists():raise ValueError('目标目录已存在，未覆盖。请选择新目录，或检查原安装记录后继续。')
    root.mkdir(parents=True)
    opener=build_opener(ProxyHandler({'http':a.proxy,'https':a.proxy}) if a.proxy else ProxyHandler({}))
    archive=root/'comfy-source.zip'
    with opener.open(f'https://codeload.github.com/Comfy-Org/ComfyUI/zip/{REVISION}',timeout=90) as r,archive.open('xb') as f:
        shutil.copyfileobj(r,f)
    source=root/'ComfyUI';source.mkdir()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            parts=Path(member.filename).parts
            if len(parts)<2:continue
            target=(source/Path(*parts[1:])).resolve()
            if not target.is_relative_to(source) or (member.external_attr>>16)&0o170000==0o120000:
                raise ValueError('源码压缩包包含异常路径，保留现场供检查。')
            if member.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(member) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
    write_json(root/'source-revision.json',dict(repository='Comfy-Org/ComfyUI',revision=REVISION,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))
    env=root/'env';subprocess.run([str(python),'-m','venv',str(env)],check=True)
    (env/'Lib/site-packages/h3_borrowed_runtime.pth').write_text(str(site)+'\n','utf-8')
    repo=Path(__file__).resolve().parents[1]
    command=[str(env/'Scripts/python.exe'),'-m','pip','install','-r',str(repo/'requirements-motion-native.txt')]
    if a.proxy:command+=['--proxy',a.proxy]
    subprocess.run(command,check=True)
    shutil.copytree(repo/'comfy_nodes/aipictures_motion',source/'custom_nodes/aipictures_motion',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    model_paths=root/'model-paths.yaml'
    write_json(model_paths,dict(aipictures_reference=dict(base_path=a.models.resolve().as_posix(),diffusion_models='diffusion_models',vae='vae'),
                               aipictures_encoder=dict(text_encoders=(h3/'models/encoder').as_posix())))
    specs=json.loads((repo/'tools/motion_models.json').read_text('utf-8'))
    models=[dict(path=str(a.models.resolve()/r['path']),bytes=r['size'],sha256=r['lfs']['oid'])
            for r in specs['files'] if not r['path'].endswith('minimax_h3_audio_vae_fp32.safetensors')]
    write_json(root/'machine.json',dict(schema_version=1,validated=False,python=str(env/'Scripts/python.exe'),
        source=str(source),model_paths=str(model_paths),models=models,width=512,height=768,source_commit=REVISION))
    print('Private source/runtime ready. Download models separately, then run and visually review an acceptance probe before registration.')


if __name__=='__main__':main()
