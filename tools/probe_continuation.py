"""Explicit real endpoint-guide acceptance; never rerun the completed parent video."""
import argparse
import json
import shutil
import threading
from pathlib import Path
from aipictures.storage import write_json
from aipictures.video_generation import generate
from aipictures.workflow_library import digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=2)
    args=p.parse_args();parent=args.parent.resolve();data=json.loads(parent.read_text('utf-8'))
    if data['status']!='completed':raise ValueError('需要已完成的真实动画。')
    args.output.mkdir(parents=True,exist_ok=False);folder=args.output.resolve()
    endpoint=parent.parent/data['frames'][-1]['image'];target=folder/'endpoint.png';shutil.copyfile(endpoint,target)
    params=dict(data['params'],seconds=args.seconds,continuation_frame=str(target),seed=(data['params']['seed']+1)%(2**64))
    params['prompt']+='\n继续上一段末尾的动作，保持相同角色、服装、构图、配色与背景，不重新开始。'
    if params.get('motion_reference'):
        from aipictures.motion_guide import inspect
        params['motion_source']=inspect(Path(params['motion_reference']))
        start=params.get('motion_start',0)+data['frame_count']/data['fps']-1/24
        params['motion_start']=start%params['motion_source']['duration'] if params.get('motion_repeat') else start
    write_json(folder/'provenance.json',dict(parent=str(parent),parent_sha256=digest(parent),
        endpoint_sha256=digest(endpoint),purpose='real continuation-guide acceptance; parent not regenerated'))
    write_json(folder/'job.json',dict(status='running',params=params))
    def event(kind,value):
        if kind in ('video_stage','progress','queued'):print(json.dumps(dict(event=kind,data=value),ensure_ascii=False,default=str),flush=True)
    try:
        result=generate(None,folder,params,threading.Event(),event)
        write_json(folder/'job.json',dict(status='completed',params=params,result=result))
        print('REAL_CONTINUATION_COMPLETE',flush=True)
    except BaseException as exc:
        write_json(folder/'job.json',dict(status='failed',params=params,error=str(exc)));raise


if __name__=='__main__':main()
