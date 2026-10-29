"""Controlled native-resolution/sampling experiments on a saved pose animation.

No post-generation sharpening, antialiasing or temporal mixing is applied.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import threading
import time

from aipictures.engine import ComfyClient
from aipictures.animation_decode import sampling_workflow,decode_sampled
from aipictures.engine_service import release_idle_models
from aipictures.generation_reference import prepare_generation_reference
from aipictures.motion_clip import body_pose
from aipictures.pose_condition import render_condition
from aipictures.storage import write_json
from aipictures.workflow_library import digest
from tools.compare_transparency_order import download_completed


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sequence',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--width',type=int,default=768)
    p.add_argument('--height',type=int,default=1024)
    p.add_argument('--sampler',default='euler')
    p.add_argument('--scheduler',default='simple')
    p.add_argument('--steps',type=int)
    p.add_argument('--resume',action='store_true')
    args=p.parse_args(); source=args.sequence.resolve(); out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True); video=out/'video';video.mkdir(exist_ok=True)
    client=ComfyClient()
    if args.resume:
        pid=json.loads((out/'submitted.json').read_text('utf-8'))['prompt_id']
        sampled=download_completed(client,pid,video);write_json(video/'sampling_result.json',sampled)
        decode_folder=video/'decode'
        if (decode_folder/'submitted.json').exists():
            dpid=json.loads((decode_folder/'submitted.json').read_text('utf-8'))['prompt_id']
            result=download_completed(client,dpid,decode_folder)
        else:result=decode_sampled(client,sampled,decode_folder,lambda *a:None,threading.Event())
        write_json(video/'result.json',result)
        print('recovered',pid,flush=True);return
    if min(args.width,args.height)<128 or max(args.width,args.height)>2048 or args.width%16 or args.height%16:
        p.error('原生画布须为 128–2048 范围内的 16 的倍数')
    manifest=json.loads((source/'sequence.json').read_text('utf-8'))
    analysis=json.loads((source/'reference_analysis.json').read_text('utf-8'))
    clip=json.loads((source/'motion.json').read_text('utf-8'))
    graph=json.loads((source/'video/workflow.json').read_text('utf-8'))
    before=deepcopy(graph); size=(args.width,args.height)
    if digest(manifest['reference'])!=manifest['reference_sha256']:
        raise ValueError('参考图已变化，无法进行受控对照。')
    report=prepare_generation_reference(manifest['reference'],out/'generation-reference.png',analysis)
    info=client.discover()
    if args.sampler not in info['samplers'] or args.scheduler not in info['schedulers']:
        raise ValueError('当前后端不支持所选采样器或调度方式。')
    graph['7']['inputs']['image']=client.upload_image(report['path'])
    pose_folder=out/'poses';pose_folder.mkdir(exist_ok=True)
    for key,node in graph.items():
        if not key.startswith('pose_image_'):continue
        i=int(key.rsplit('_',1)[1])
        pose=json.loads((source/'poses'/f'pose_{i:03d}.json').read_text('utf-8'))
        write_json(pose_folder/f'pose_{i:03d}.json',pose)
        path=pose_folder/f'pose_{i:03d}.png'
        render_condition(body_pose(pose,clip['base_rig']),clip['base_rig'],size).save(path)
        node['inputs']['image']=client.upload_image(path,subfolder='AIPictures/detail_tests')
    graph['8']['inputs'].update(width=args.width,height=args.height)
    graph['11']['inputs'].update(sampler_name=args.sampler,scheduler=args.scheduler)
    if args.steps is not None:graph['11']['inputs']['steps']=args.steps
    # Reject changes outside the intended experiment, including accidental seed,
    # prompt, model, pose topology or decoder changes.
    check=deepcopy(graph)
    check['7']=before['7']
    for key in before:
        if key.startswith('pose_image_'):check[key]=before[key]
    for key in ('width','height'):check['8']['inputs'][key]=before['8']['inputs'][key]
    for key in ('sampler_name','scheduler','steps'):check['11']['inputs'][key]=before['11']['inputs'][key]
    if check!=before:raise AssertionError('实验改变了未计划的生成参数。')
    graph=sampling_workflow(graph)
    write_json(video/'workflow.json',graph)
    experiment={'baseline':str(source),'seed':graph['11']['inputs']['seed'],'canvas':list(size),
        'sampler':args.sampler,'scheduler':args.scheduler,'steps':graph['11']['inputs']['steps'],
        'reference':report,'raw_only':True,'status':'running',
        'controls':'same reference content, exact joint coordinates, model, seed, prompts, frame count and VAE'}
    write_json(out/'experiment.json',experiment);started=time.monotonic()
    experiment['initial_cache_cleanup']=release_idle_models(client)
    cancel=threading.Event()
    sampled=client.generate(graph,video,lambda k,d:print(k,d,flush=True) if k in ('queued','progress') else None,
        cancel,timeout=float('inf'),allow_latent_only=True,
        submitted=lambda pid:write_json(out/'submitted.json',{'prompt_id':pid}))
    write_json(video/'sampling_result.json',sampled)
    result=decode_sampled(client,sampled,video/'decode',lambda *a:None,cancel)
    write_json(video/'result.json',result)
    experiment.update(status='completed',prompt_id=result['prompt_id'],frame_count=len(result['images']),
        elapsed_seconds=round(time.monotonic()-started,3))
    write_json(out/'experiment.json',experiment);print('completed',experiment,flush=True)


if __name__=='__main__':main()
