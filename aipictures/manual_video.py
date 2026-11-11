"""One new audiovisual segment per click, preserving the delivered prior video."""
import json
import math
import os
import shutil
from pathlib import Path
import numpy as np
from .storage import write_json
from .workflow_library import digest
from .engine import Cancelled


def freeze(source,target):
    source=Path(source).resolve();target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise ValueError('续接快照已存在，未覆盖。')
    try:os.link(source,target)
    except OSError:shutil.copyfile(source,target)
    return target.resolve()


def generate(folder,params,cancel,emit):
    from .h3_backend import generate as backend
    from .video_io import encode_native_rgb
    from .video_audio import package
    from .native_long_worker import join
    folder=Path(folder);seconds=params['seconds'];continuing=bool(params.get('continue_from'))
    if not 2<=seconds<=(7 if continuing else 8):raise ValueError('新视频单段2–8秒，原生续接单段2–7秒。')
    if (folder/'manual-video.json').exists():raise ValueError('该段已有运行记录，不重复提交或覆盖。')
    previous=None;previous_rgb=None;previous_count=0
    receipt=dict(version=1,status='preparing',user_request=params.get('source_brief',params['prompt']),segment_seconds=seconds,
        automatic_multi_segment=False,context_frames=22 if continuing else 0)
    if continuing:
        manifest=Path(params['continue_from'])
        if digest(manifest)!=params.get('continue_manifest_sha256'):raise ValueError('前一段记录发生变化，未启动续接。')
        old=json.loads(manifest.read_text('utf-8'))
        if old['status']!='completed' or not old.get('native_rgb_source') or old.get('fps')!=24:
            raise ValueError('只能接续本软件保存完整原生画面的H3视频。')
        source=Path(old['source_video'])
        if old.get('source_sha256') and digest(source)!=old['source_sha256']:raise ValueError('前一段视频已变化，未启动续接。')
        previous=freeze(source,folder/'previous'/'video.mp4')
        previous_rgb=freeze(old['native_rgb_source'],folder/'previous'/'rgb.npy')
        previous_record=freeze(manifest,folder/'previous'/'manifest.json')
        previous_count=int(old['frame_count'])
        rgb_sha=digest(previous_rgb)
        if old.get('native_rgb_sha256') and rgb_sha!=old['native_rgb_sha256']:raise ValueError('前段原生画面发生变化，未启动续接。')
        receipt.update(previous_manifest=str(manifest),frozen_previous_manifest=str(previous_record),previous_sha256=digest(previous),previous_rgb_sha256=rgb_sha,previous_frames=previous_count)
    segment=folder/'new_segment';segment.mkdir()
    frames=(22+17*math.ceil(seconds*24/17)) if continuing else 5+17*math.ceil((seconds*24-5)/17)
    if frames>192:raise ValueError('本段超出已验证的原生上下文窗口。')
    request=dict(params,h3_two_pass=True,h3_frames=frames,creation_kind='long_segment',seconds=frames/24)
    if previous:request.update(reference=None,h3_continue_video=str(previous),h3_continue_sha256=digest(previous))
    receipt.update(status='generating',model_frames=frames);write_json(folder/'manual-video.json',receipt)
    write_json(segment/'params.json',request)
    result=backend(segment,request,cancel,emit)
    if not result.get('native_rgb'):raise ValueError('本段缺少原生画面，未使用末帧重绘冒充音画续接。')
    if previous_rgb and digest(previous_rgb)!=receipt['previous_rgb_sha256']:raise ValueError('生成期间前段原生画面发生变化，未合并。')
    new=np.load(result['native_rgb'],mmap_mode='r',allow_pickle=False);new_count=round(seconds*24)
    old_rgb=np.load(previous_rgb,mmap_mode='r',allow_pickle=False) if previous_rgb else None
    try:
        if len(new)<new_count or new.dtype!=np.uint8:raise ValueError('本段原生画面不足，未用定格补齐。')
        if old_rgb is not None and (old_rgb.shape[1:]!=new.shape[1:] or len(old_rgb)<previous_count):raise ValueError('续接画布与前段不一致，请保持尺寸或新建视频。')
        count=previous_count+new_count;target=folder/'rgb.npy'
        output=np.lib.format.open_memmap(target,mode='w+',dtype=np.uint8,shape=(count,*new.shape[1:]))
        try:
            for start in range(0,previous_count,24):
                if cancel.is_set():raise Cancelled('合并已取消，原视频保留。')
                output[start:min(start+24,previous_count)]=old_rgb[start:min(start+24,previous_count)]
            output[previous_count:]=new[:new_count];output.flush()
        finally:output._mmap.close()
    finally:
        new._mmap.close()
        if old_rgb is not None:old_rgb._mmap.close()
    if params.get('audio_mode')=='none':
        video=folder/'video_silent.mp4';encode_native_rgb(target,video,24,cancel,emit,frame_count=count)
    else:
        # Compatibility with existing audiovisual records; normal CG is silent.
        encode_native_rgb(Path(result['native_rgb']),segment/'video_silent.mp4',24,cancel,emit,frame_count=new_count)
        tracks=package(segment,Path(result['video']),seconds,params,cancel)
        sources=([dict(video=str(previous))] if previous else [])+[dict(video=tracks['video'])]
        delivery=dict(params,seconds=count/24)
        video=join(folder,delivery,sources,cancel,emit)
    receipt.update(status='completed',frame_count=count,total_seconds=count/24,new_frames=new_count,
        previous_pixels_unchanged=True,video=str(video),video_sha256=digest(video),new_segment=result)
    write_json(folder/'manual-video.json',receipt)
    return dict(video=str(video),native_rgb=str(target.resolve()),backend='H3/manual-AV-continuation',
        manual_session=str(folder/'manual-video.json'),frame_count=count,total_seconds=count/24,warnings=[])
