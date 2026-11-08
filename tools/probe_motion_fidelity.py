"""Prepare, then explicitly run one source-motion comparison; no automatic rerolls."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import threading

from aipictures.motion_prompt import FORMAT,generated_constraints
from aipictures.storage import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=4.)
    parser.add_argument('--watch-data',type=Path)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if not 2<=args.seconds<=8:parser.error('Use the currently supported 2–8 second clip budget.')
    baseline=json.loads((args.baseline/'video.json').read_text('utf-8'))
    if baseline['status']!='completed':parser.error('The baseline must be a completed clip.')
    plan=json.loads((args.baseline/'intent-plan.json').read_text('utf-8'))
    # A reviewed original request provides provenance: never filter an unknown
    # user's manually edited positive or negative prompt during a comparison.
    if baseline['params']['prompt']!=plan['plan']['positive_prompt'] or baseline['params']['negative']!=plan['plan']['negative_prompt']:
        parser.error('The baseline contains manual edits; prepare the comparison requirements explicitly.')
    params=deepcopy(baseline['params']);params['seconds']=args.seconds
    explicit=plan['request']['brief']+'\n'+plan['request'].get('reference_usage','')
    params['prompt'],params['negative']=generated_constraints(params['prompt'],explicit,plan['request']['negative'])
    params['user_prompt']=params['prompt'];params['motion_prompt_format']=FORMAT
    if any(Path(params[key]).suffix=='.json' for key in ('reference','motion_reference')):
        parser.error('This evidence probe currently accepts a video/GIF, not a frame manifest.')
    args.folder.mkdir(parents=True,exist_ok=False)
    for key in ('reference','motion_reference'):
        source=Path(params[key]);target=args.folder/(key+source.suffix)
        shutil.copyfile(source,target);params[key]=str(target.resolve())
    write_json(args.folder/'comparison.json',dict(baseline=str(args.baseline.resolve()),seed=params['seed'],
        baseline_seconds=baseline['params']['seconds'],candidate_seconds=args.seconds,
        exact_duration_ab=args.seconds==baseline['params']['seconds'],changes=['source-edit context','generated constraints'],
        no_new_weights=True,run_requested=args.run))
    write_json(args.folder/'job.json',dict(kind='video',status='prepared',params=params),durable=True)
    if not args.run:print('Prepared; no GPU job was submitted.',flush=True);return
    from aipictures.video_generation import generate
    from aipictures.gpu_watch import read_json,process_alive
    context_path=args.watch_data/'gpu-watch-context.json' if args.watch_data else None
    previous=read_json(context_path) if context_path else {}
    owns_context=bool(context_path and (not previous or process_alive(previous.get('pid')) is False))
    cancel=threading.Event()
    def context(state,stage,progress=0,maximum=100):
        if owns_context:
            write_json(context_path,dict(pid=os.getpid(),folder=str(args.folder.resolve()),state=state,
                stage=stage,progress=progress,maximum=maximum,queued_count=0,
                updated_at=datetime.now().astimezone().isoformat()),durable=True)
    def event(kind,data):
        with (args.folder/'events.jsonl').open('a',encoding='utf-8') as out:
            out.write(json.dumps(dict(time=datetime.now().astimezone().isoformat(),event=kind,data=data),ensure_ascii=False,default=str)+'\n')
            out.flush()
        if kind=='video_stage':context('running',data.get('message',''))
        if kind=='progress':context('running','采样',data.get('value',0),data.get('max',100))
        if kind in ('video_stage','progress','execution_error'):
            print(json.dumps(dict(event=kind,data=data),ensure_ascii=True,default=str),flush=True)
    context('running','动作精度实测准备')
    write_json(args.folder/'job.json',dict(kind='video',status='running',params=params),durable=True)
    try:
        result=generate(None,args.folder,params,cancel,event)
        write_json(args.folder/'job.json',dict(kind='video',status='completed',params=params,result=result),durable=True)
        context('completed','动作精度实测完成',100)
        print('FIDELITY_PROBE_COMPLETE',flush=True)
    except BaseException as exc:
        cancel.set();context('failed','动作精度实测未完成')
        write_json(args.folder/'job.json',dict(kind='video',status='failed',params=params,error=str(exc)),durable=True)
        raise


if __name__=='__main__':main()
