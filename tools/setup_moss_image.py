"""Install a pinned MOSS research runtime without touching existing model engines."""
import argparse,json,shutil,subprocess,zipfile
from pathlib import Path
from urllib.request import build_opener,ProxyHandler,install_opener
from .prepare_style_models import install_file,digest
from aipictures.storage import write_json

SOURCE='c1eece62cbf1805d4f64286d7f5592e6a215e6ba'
ARCHIVE_SHA='204c1a0d17a5058959192d699736aad59a8c57284042660297f1e0b488270c04'
REV='2929efe3cdd506c0a430bcfca70a9a8d805cc095'
FILES=[
 ('diffusion_models/moss_image_sft_int8_convrot.safetensors',5413698958,'b4d1475bc7eeffd7b809e82ea13a1fba1fb85c4e18365af3813722faa5c0fe4f'),
 ('text_encoders/qwen3.5_9b_w4a8_gptq.safetensors',7343591088,'4cc6a1543ad2061806da46f35f90cadb4801dcba246c44782cf42ec0feb6407c'),
 ('vae/flux2-vae_small.safetensors',249521340,'d8d52ba036475f5fb07c8b435e176d3d97ebfa82f0d1a1c317f9cc1e25bd013b'),
 ('loras/moss_image_edit_lora_rank_64_bf16.safetensors',297382216,'17a48b8c605dcffdedb92a2b887d18cf316505be90802717669fb6556098dcdf')]


def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--models',type=Path,required=True)
 p.add_argument('--source-archive',type=Path,required=True);p.add_argument('--borrow-python',type=Path,required=True);p.add_argument('--proxy');a=p.parse_args()
 root=a.root.resolve();models=a.models.resolve()
 if digest(a.source_archive)!=ARCHIVE_SHA:raise ValueError('Pinned ComfyUI archive checksum mismatch')
 if a.proxy:install_opener(build_opener(ProxyHandler({'http':a.proxy,'https':a.proxy})))
 if not (root/'machine.json').exists():
  root.mkdir(parents=True,exist_ok=False);source=root/'ComfyUI';source.mkdir()
  with zipfile.ZipFile(a.source_archive) as archive:
   for item in archive.infolist():
    parts=Path(item.filename).parts
    if len(parts)<2:continue
    target=(source/Path(*parts[1:])).resolve()
    if not target.is_relative_to(source) or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe archive')
    if item.is_dir():target.mkdir(parents=True,exist_ok=True)
    else:
     target.parent.mkdir(parents=True,exist_ok=True)
     with archive.open(item) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
  env=root/'env';subprocess.run([str(a.borrow_python),'-m','venv',str(env)],check=True)
  site=a.borrow_python.resolve().parents[1]/'Lib/site-packages'
  (env/'Lib/site-packages/borrowed_runtime.pth').write_text('import site; site.addsitedir('+repr(str(site))+')\n','utf-8')
  node=source/'custom_nodes/aipictures_moss';node.mkdir()
  repo=Path(__file__).resolve().parents[1]
  for name in ['stream_weights.py','conditioning.py']:shutil.copy2(repo/'comfy_nodes/aipictures_motion'/name,node/name)
  shutil.copy2(repo/'comfy_nodes/aipictures_moss/__init__.py',node/'__init__.py')
  paths=root/'model-paths.yaml';write_json(paths,dict(moss=dict(base_path=models.as_posix(),**{k:k for k in ['diffusion_models','text_encoders','vae','loras']})))
  config=dict(validated=False,python=str(env/'Scripts/python.exe'),source=str(source),model_paths=str(paths),source_commit=SOURCE,model_revision=REV,models=[])
  write_json(root/'machine.json',config)
 config=json.loads((root/'machine.json').read_text('utf-8'))
 if config['source_commit']!=SOURCE or config['model_revision']!=REV:raise ValueError('Resume specification changed')
 if shutil.disk_usage(models.parent).free<sum(size for name,size,_ in FILES if not (models/name).exists())+4*1024**3:raise ValueError('Insufficient disk space')
 for name,size,sha in FILES:
  row=install_file(models/name,dict(bytes=size,sha256=sha,url=f'https://huggingface.co/Comfy-Org/MOSS-Image/resolve/{REV}/{name}'))
  config['models']=[r for r in config['models'] if r['path']!=row['path']]+[row];write_json(root/'machine.json',config)
 write_json(root/'installation.json',dict(models=config['models'],publisher_verified=True,bytes=sum(s for _,s,_ in FILES),registered=False))
 print('MOSS runtime installed; no production engine registered.',flush=True)


if __name__=='__main__':main()
