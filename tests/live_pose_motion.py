"""Actual pose-conditioned inference. Raw/static switches are diagnostic only, not UI routes."""
import argparse
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from aipictures.engine import ComfyClient
from aipictures.pose_animation import generate,check_models
from aipictures.storage import DATA,write_json
from aipictures.animation_actions import ACTIONS


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--reference',required=True)
    parser.add_argument('--action',choices=ACTIONS,default='walk'); parser.add_argument('--steps',type=int,default=20)
    parser.add_argument('--fast',action='store_true'); parser.add_argument('--raw',action='store_true')
    parser.add_argument('--static',action='store_true'); args=parser.parse_args()
    root=DATA/('pose-tests' if args.raw else 'animations')/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
    root.mkdir(parents=True); started=time.monotonic(); client=ComfyClient(); info=client.discover()
    check_models(info['object_info'],args.fast); events=[]
    def emit(kind,data):
        if kind in ('reference_stage','frame_ready') or kind=='pose_video_event' and data['event'] in ('queued','progress','execution_error'):
            print(json.dumps({'event':kind,'data':data},ensure_ascii=True),flush=True)
        if kind=='pose_video_event' and data['event']=='progress': events.append(data['data'])
    print('Folder:',root,flush=True)
    result=generate(client,root,'参考图中的同一角色，侧视，全身，保持一致',
        '多余手臂，多余腿部，多余脚掌，重复鞋尖，双层鞋底，重影，文字，水印',20261029,8,8,emit,
        threading.Event(),args.reference,steps=args.steps,action=args.action,static_test=args.static,fast=args.fast,raw_only=args.raw)
    write_json(root/'acceptance.json',{'functional_execution_passed':True,'visual_review':'pending',
        'static':args.static,'action':args.action,'fast':args.fast,'raw_only':args.raw,
        'steps':args.steps,'events':len(events),'elapsed_seconds':round(time.monotonic()-started,1),'result':result})
    print(json.dumps({'folder':str(root),'elapsed':round(time.monotonic()-started,1),'visual_review':'pending'},ensure_ascii=True),flush=True)


if __name__=='__main__': main()
