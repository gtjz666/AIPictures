"""One explicit local MOSS inference; no registration and no automatic retries."""
import argparse,json,shutil,threading
from pathlib import Path
from aipictures import moss_image as moss
from aipictures.moss_runtime import generate
from aipictures.storage import write_json
from aipictures.workflow_library import digest


def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['layout','edit'],default='layout')
 p.add_argument('--reference',type=Path,action='append',default=[]);p.add_argument('--prompt');p.add_argument('--draft',type=Path);p.add_argument('--width',type=int,default=1024);p.add_argument('--height',type=int,default=1024);p.add_argument('--seed',type=int,default=20261117);a=p.parse_args()
 folder=a.output.resolve();folder.mkdir(parents=True,exist_ok=False)
 draft=json.loads(a.draft.read_text('utf-8')) if a.draft else moss.draft()
 if a.prompt:draft['summary']['caption']=a.prompt
 params=dict(mode='moss_image',model_family='moss_image',backend='standalone',moss_mode=a.mode,positive=a.prompt or draft['summary']['caption'],negative='',width=a.width,height=a.height,seed=a.seed,steps=30 if a.mode=='edit' else 25,cfg=4. if a.mode=='edit' else 2.5,layout=draft,references={},moss_settings=json.loads(a.config.read_text('utf-8')),prompt_expander=False)
 for i,path in enumerate(a.reference,1):
  sha=digest(path);target=folder/'references'/f'{i}{path.suffix}';target.parent.mkdir(exist_ok=True);shutil.copy2(path,target)
  if digest(target)!=sha:raise ValueError('Input changed during copy')
  params['references'][i]=dict(path=str(target),sha256=sha)
 write_json(folder/'request.json',params,durable=True)
 def event(kind,data):
  if kind=='moss_stage':print(data['message'],flush=True)
  elif kind=='progress':print(f"step {data['value']}/{data['max']}",flush=True)
 try:
  result=generate(folder,params,threading.Event(),event,research=True)
  write_json(folder/'acceptance.json',dict(completed=True,images=result['images'],elapsed_seconds=result['elapsed_seconds'],protocol=moss.PROTOCOL,quality_review='pending'),durable=True)
  print('MOSS_COMPLETE',result['images'],flush=True)
 except BaseException as exc:write_json(folder/'failure.json',dict(error=str(exc),type=type(exc).__name__),durable=True);raise


if __name__=='__main__':main()
