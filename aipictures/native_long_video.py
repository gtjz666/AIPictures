"""Bounded H3 audiovisual context continuation, not repeated independent clips."""
import json
import math
import os
import subprocess
import sys
from uuid import uuid4
from pathlib import Path
import numpy as np
from .storage import write_json
from .workflow_library import digest
from .engine import Cancelled
from .video_chain import job_lock

FPS=24


def plan(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 9<=seconds<=45 or seconds!=int(seconds):
        raise ValueError('分段视频支持9–45秒，请使用整数秒。')
    # <=192 model frames per part, including the 22 frozen audiovisual context frames.
    count=math.ceil((seconds-8)/7);rest=max(seconds-8,5*count)
    lengths=[int(rest)//count+(i<int(rest)%count) for i in range(count)]
    lengths.insert(0,seconds-rest);shown=0;parts=[]
    for i,length in enumerate(lengths):
        target=round(sum(lengths[:i+1])*FPS)
        frames=5+17*math.ceil((target-5)/17) if i==0 else 22+17*math.ceil((target-shown)/17)
        new=frames if i==0 else frames-22
        if frames>192 or i and new<119:raise ValueError('此分段计划超出本机已选工作范围。')
        parts.append(dict(index=i,start_frame=shown,frames=frames,new_frames=new,start=shown/FPS,end=min(seconds,(shown+new)/FPS)))
        shown+=new
    if len(parts)>8:raise ValueError('连续片段过多，请缩短时长。')
    return parts


def segment_prompt(params,part):
    from .video_script import prompt
    script=params['short_script'];rows=[]
    for shot in script['shots']:
        start=max(shot['start'],part['start']);end=min(shot['end'],part['end'])
        if end>start:rows.append(dict(shot,start=start-part['start'],end=end-part['start']))
    local=dict(script,shots=rows,duration_seconds=part['end']-part['start'])
    text=prompt(local)
    if part['index']:text+='\n承接已有音画上下文。除用户明确要求改变的部分外，保持主体、服装、场景、光照、运动方向、动作速度和配乐节奏连续；优先执行本段脚本中的变化，不重复开场。'
    if params.get('prompt')!=prompt(script):text+='\n用户补充或修改的要求：'+params['prompt']
    return text


def generate(folder,params,cancel,emit):
    from .h3_backend import generate as backend
    folder=Path(folder);parts=plan(params['seconds']);path=folder/'native-chain.json'
    frozen={k:v for k,v in params.items() if k!='resume_chain'}
    import hashlib
    signature=hashlib.sha256(json.dumps(frozen,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with job_lock(folder):
        state=dict(version=2,status='running',signature=signature,plan=parts,parts=[],video_blending=False,context_frames=22)
        if path.exists():
            state=json.loads(path.read_text('utf-8'))
            if not params.get('resume_chain') or state['signature']!=signature or state['plan']!=parts:raise ValueError('已有长视频记录，请保留原设置后显式继续；不会重复生成。')
        previous=None;results=[]
        try:
            for part in parts:
                if cancel.is_set():raise Cancelled('长视频已取消，已完成片段保留。')
                prior=next((r for r in state['parts'] if r['index']==part['index']),None)
                target=folder/prior['folder'] if prior and prior.get('folder') else folder/'native_segments'/f'{part["index"]+1:02d}'
                saved=target/'backend-result.json'
                if saved.is_file():
                    if prior is None:raise ValueError('发现不属于当前记录的片段，未自动复用或覆盖。')
                    result=json.loads(saved.read_text('utf-8'))
                    if digest(Path(result['video']))!=result['video_sha256']:raise ValueError('已完成片段变化，停止续接。')
                    if result.get('native_rgb_sha256') and digest(Path(result['native_rgb']))!=result['native_rgb_sha256']:raise ValueError('已完成片段原始画面变化，停止续接。')
                    prior.update(status='completed',result=result);write_json(path,state)
                else:
                    attempt=1
                    if target.exists():
                        if not params.get('resume_chain') or not prior:raise ValueError('当前片段有未完成记录，请先核查日志；不自动重跑。')
                        attempt=prior.get('attempt',1)+1
                        target=folder/'native_segments'/f'{part["index"]+1:02d}_attempt_{attempt:02d}'
                    target.mkdir(parents=True)
                    saved=target/'backend-result.json'
                    row=dict(index=part['index'],attempt=attempt,status='running',folder=str(target.relative_to(folder)))
                    if prior:state['parts'].remove(prior)
                    state['parts'].append(row);state['status']='running';write_json(path,state)
                    request=dict(params,prompt=segment_prompt(params,part),creation_kind='long_segment',h3_two_pass=True,
                        h3_frames=part['frames'],seconds=part['frames']/FPS,seed=(params['seed']+part['index'])%(2**64))
                    if previous:request.update(reference=None,h3_continue_video=previous['video'],h3_continue_sha256=previous['video_sha256'])
                    write_json(target/'params.json',request)
                    def progress(kind,data):
                        if kind=='progress':emit('chain_progress',dict(fraction=(part['index']+data['value']/max(1,data['max']))/len(parts),message=f'第{part["index"]+1}/{len(parts)}段 · 生成中'))
                        elif kind=='video_stage':emit(kind,dict(message=f'第{part["index"]+1}/{len(parts)}段 · '+data['message']))
                        else:emit(kind,data)
                    emit('video_stage',dict(message=f'第{part["index"]+1}/{len(parts)}段 · 原生音画续接'))
                    result=backend(target,request,cancel,progress)
                    if not result.get('native_rgb'):raise ValueError('长视频片段缺少原生RGB，停止合并。')
                    result['video_sha256']=digest(Path(result['video']));result['native_rgb_sha256']=digest(Path(result['native_rgb']));write_json(saved,result)
                    row.update(status='completed',result=result);write_json(path,state)
                array=np.load(result['native_rgb'],mmap_mode='r')
                try:
                    if len(array)!=part['new_frames']:raise ValueError('原生续接输出帧数不符，未合并。')
                finally:array._mmap.close()
                previous=result;results.append(result)
            first=np.load(results[0]['native_rgb'],mmap_mode='r');shape=first.shape[1:];first._mmap.close()
            rgb=folder/'rgb.npy';count=round(params['seconds']*FPS)
            # A completed assembly is checked and reused. Interrupted assemblies
            # have unique names, so resuming never overwrites their evidence.
            if rgb.is_file():
                existing=np.load(rgb,mmap_mode='r');cursor=0
                try:
                    if existing.shape!=(count,*shape) or existing.dtype!=np.uint8:raise ValueError('已有合并画面不完整，保留原文件，未覆盖。')
                    for result in results:
                        source=np.load(result['native_rgb'],mmap_mode='r')
                        try:
                            n=min(len(source),count-cursor)
                            if not np.array_equal(existing[cursor:cursor+n],source[:n]):raise ValueError('已有合并画面与片段不一致，未覆盖。')
                            cursor+=n
                        finally:source._mmap.close()
                finally:existing._mmap.close()
            else:
                temporary=folder/f'rgb-assembling-{uuid4().hex[:8]}.npy';cursor=0
                destination=np.lib.format.open_memmap(temporary,mode='w+',dtype=np.uint8,shape=(count,*shape))
                try:
                    for result in results:
                        source=np.load(result['native_rgb'],mmap_mode='r')
                        try:
                            if source.dtype!=np.uint8 or source.shape[1:]!=shape:raise ValueError('片段画布不一致。')
                            for frame in source:
                                if cancel.is_set():raise Cancelled('长视频合并已取消。')
                                if cursor>=count:break
                                destination[cursor]=frame;cursor+=1
                        finally:source._mmap.close()
                    destination.flush()
                finally:destination._mmap.close()
                if cursor==count:temporary.rename(rgb)
            if cursor!=count:raise ValueError('合并后的画面长度不完整。')
            from .native_long_worker import join
            video=join(folder,params,results,cancel,emit)
            state.update(status='completed',frame_count=count);write_json(path,state)
            return dict(video=str(video),native_rgb=str(rgb.resolve()),backend='H3/native-AV-continuation',chain=str(path),warnings=[])
        except BaseException as exc:
            state.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));write_json(path,state);raise
