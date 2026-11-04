"""Serial H3 clips with endpoint conditioning and resumable, lossless frame assembly."""
import hashlib
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image

from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest
from .prompt_timeline import remove_owned_timeline

FPS=24
CLIP_SECONDS=8.  # Retain the validated working set, even for a long requested output.
MAX_SECONDS=7200.


@contextmanager
def job_lock(folder:Path):
    """An OS-held lease is released on a crash; another window cannot resume a live chain."""
    with (folder/'chain.lock').open('a+b') as handle:
        handle.seek(0,2)
        if not handle.tell():handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise ValueError('此长动画仍由其他窗口处理，不能重复启动。') from exc
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)


def plan(seconds:float,clip_seconds:float=CLIP_SECONDS)->list[dict]:
    if not math.isfinite(seconds) or not 2<=seconds<=MAX_SECONDS:raise ValueError('动画时长应为2秒至2小时。')
    if not 2<=clip_seconds<=14:raise ValueError('分段长度应为2–14秒，为H3对齐和衔接预留空间。')
    total=math.ceil(seconds*FPS)
    max_aligned=5+17*math.floor((clip_seconds*FPS-5)/17)
    count=math.ceil(total/(max_aligned-1))  # Reserve one endpoint guide frame in later clips.
    # Balance the tail: a 16.1 s request must not end with an unusable 0.1 s model call.
    cuts=[round(i*total/count) for i in range(count+1)]
    return [dict(index=i,start_frame=cuts[i],frames=cuts[i+1]-cuts[i],
                 start=cuts[i]/FPS,end=cuts[i+1]/FPS) for i in range(count)]


def segment_params(params:dict,part:dict,endpoint:Path|None)->dict:
    out=dict(params);out.pop('resume_chain',None)
    overlap=int(endpoint is not None)
    out['seconds']=max(2.,(part['frames']+overlap)/FPS)
    out['seed']=(int(params['seed'])+part['index'])%(2**64)
    if endpoint:out['continuation_frame']=str(endpoint.resolve())
    if params.get('motion_reference'):
        start=params.get('motion_start',0.)+part['start']-overlap/FPS
        if params.get('motion_repeat'):start%=params['motion_source']['duration']
        out['motion_start']=max(0.,start)
    text=remove_owned_timeline(params['prompt'])
    text+=f"\n本段对应完整动画的{part['start']:.3f}–{part['end']:.3f}秒。保持角色、配色、光照、场景和镜头连续，承接前段末尾姿态，不重新开始整个动作。"
    rows=[]
    source_clock=params.get('motion_timeline_clock')=='source' and params.get('motion_reference')
    window=out.get('motion_start',0.) if source_clock else part['start']
    length=part['frames']/FPS
    for row in params.get('motion_timeline',[]):
        if source_clock and params.get('motion_repeat'):
            # Describe one cycle on its original clock; the actual guide handles repetition.
            rows.append(f"参考{row['start']:.3f}–{row['end']:.3f}秒：{row['description']}")
            continue
        a=max(window,row['start']);b=min(window+length,row['end'])
        shift=0. if source_clock else overlap/FPS
        if b>a:rows.append(f"本段{a-window+shift:.3f}–{b-window+shift:.3f}秒：{row['description']}")
    if source_clock and params.get('motion_repeat'):text+=f"\n参考时间线以{params['motion_source']['duration']:.3f}秒为一轮重复，本段参考起点为{window:.3f}秒。"
    if rows:text+='\n优先执行本段时序：\n'+'\n'.join(rows)
    out['prompt']=text
    return out


def seam_error(first:Path,second:Path)->float:
    with Image.open(first) as a,Image.open(second) as b:
        if a.size!=b.size:raise ValueError('续接片段画布不同，停止拼接；各段结果保留。')
        return round(float(np.abs(np.asarray(a.convert('RGB'),dtype=np.float32)-np.asarray(b.convert('RGB'),dtype=np.float32)).mean()/255),6)


def generate(folder:Path,params:dict,cancel,emit)->dict:
    with job_lock(Path(folder)):
        return _generate(Path(folder),params,cancel,emit)


def _generate(folder:Path,params:dict,cancel,emit)->dict:
    from .video_io import native_rgb_frames,preview_frames,encode_pngs
    from .h3_backend import generate as plain
    from .motion_native_backend import generate as reference
    folder=Path(folder);path=folder/'chain.json'
    frozen={k:v for k,v in params.items() if k!='resume_chain'}
    signature=hashlib.sha256(json.dumps(frozen,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    parts=plan(params['seconds']);state=dict(schema_version=1,signature=signature,status='running',
        requested_seconds=params['seconds'],fps=FPS,plan=parts,parts=[],seams=[],temporal_blending=False,
        continuity='previous endpoint as first-frame guide; no motion history',warnings=[])
    if path.exists():
        if not params.get('resume_chain'):raise ValueError('已有分段任务，请从记录中选择继续，不重复生成。')
        state=json.loads(path.read_text('utf-8'))
        if state.get('signature')!=signature or state.get('plan')!=parts:raise ValueError('续接参数或素材不一致；请保留原任务设置。')
    def save():write_json(path,state)
    paths=[];backend=reference if params.get('motion_reference') else plain
    try:
        for part in parts:
            if cancel.is_set():raise Cancelled('长动画已取消，已完成片段保留，可从记录继续。')
            i=part['index'];prior=next((r for r in state['parts'] if r['index']==i),None)
            if prior and prior['status']=='completed':
                saved=[folder/p for p in prior['frames']]
                if len(saved)!=part['frames'] or [digest(p) for p in saved]!=prior['sha256']:
                    raise ValueError(f'第{i+1}段已保存的帧缺失或变化；不会自动重做或覆盖。')
                paths.extend(saved);continue
            # Incomplete attempts are kept. An explicit resume starts only the unfinished part.
            endpoint=paths[-1] if paths else None
            request=segment_params(params,part,endpoint)
            recover=folder/prior['folder'] if prior else None
            if recover and (recover/'backend-result.json').is_file():
                target=recover;row=prior
                if json.loads((target/'params.json').read_text('utf-8'))!=request:
                    raise ValueError('已完成采样的片段参数不同，不自动重做。')
            else:
                attempts=1 if not prior else prior['attempt']+1
                target=folder/'segments'/f'{i+1:04d}'/f'attempt_{attempts:02d}';target.mkdir(parents=True,exist_ok=False)
                row=dict(index=i,attempt=attempts,status='running',folder=str(target.relative_to(folder)))
                if prior:state['parts'].remove(prior)
                state['parts'].append(row);write_json(target/'params.json',request)
            state['status']='running';save()
            def progress(kind,data):
                if kind=='progress':
                    emit('chain_progress',dict(fraction=(i+.8*data['value']/max(1,data['max']))/len(parts),
                        message=f"第{i+1}/{len(parts)}段 · 采样中"))
                elif kind in ('video_stage','video_decode_progress'):
                    emit('video_stage',dict(message=f"第{i+1}/{len(parts)}段 · "+data.get('message','解码动画…')))
                else:emit(kind,data)
            emit('chain_progress',dict(fraction=i/len(parts),message=f'第{i+1}/{len(parts)}段 · 准备中'))
            if (target/'backend-result.json').is_file():result=json.loads((target/'backend-result.json').read_text('utf-8'))
            else:
                result=backend(target,request,cancel,progress)
                write_json(target/'backend-result.json',result)
            native=True
            preview=target/'preview_frames'
            if preview.exists():preview=target/('preview_frames_'+uuid4().hex[:8])
            if result.get('native_frames'):frames=[Path(p) for p in result['native_frames']]
            elif result.get('native_rgb'):frames=native_rgb_frames(Path(result['native_rgb']),preview,cancel,progress)
            else:
                frames,fps=preview_frames(Path(result['video']),preview,cancel,progress);native=False
                if fps!=FPS:raise ValueError('片段帧率不是24FPS，不能无损续接。')
            skip=int(endpoint is not None)
            selected=frames[skip:skip+part['frames']]
            if len(selected)!=part['frames']:raise ValueError('片段帧数不足，保留结果，未合并错误时长。')
            if endpoint:
                error=seam_error(endpoint,selected[0]);state['seams'].append(dict(part=i+1,mean_rgb_delta=error))
                if error>.12:state['warnings'].append(f'第{i+1}段衔接画面变化较大，请预览检查；未做混帧掩盖。')
            row.update(status='completed',frames=[str(p.resolve().relative_to(folder.resolve())) for p in selected],
                sha256=[digest(p) for p in selected],source_result=result,native_rgb_preserved=native,
                seed=request['seed'],dropped_guide_frames=skip,trimmed_alignment_frames=len(frames)-skip-len(selected))
            paths.extend(selected);save()
        target=folder/'animation_master.mp4';encode_pngs(paths,target,FPS,cancel)
        state['status']='completed';state['frame_count']=len(paths);save()
        return dict(video=str(target.resolve()),native_frames=[str(p.resolve()) for p in paths],
            frame_sha256=[digest(p) for p in paths],backend='H3/serial-continuation',chain=str(path.resolve()),
            native_rgb_preserved=all(r['native_rgb_preserved'] for r in state['parts']),warnings=state['warnings'])
    except BaseException as exc:
        state.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));save();raise
