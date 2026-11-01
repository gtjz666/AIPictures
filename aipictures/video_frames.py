"""Decode local videos into independent native-size sprite assets, without frame blending."""
import time
import threading
from pathlib import Path

import av
from PIL import Image

from .engine import Cancelled
from .loop_frames import cycle_indices
from .storage import write_json
from .workflow_library import digest


def extract_video(source: Path, folder: Path, count: int, fps: int, loop: bool,
                  transparent: bool, cancel: threading.Event, emit, *, sampling: str='uniform') -> dict:
    source,folder=Path(source).resolve(),Path(folder)
    if not source.is_file() or source.suffix.lower() not in ('.mp4','.mov','.webm','.mkv','.avi','.gif'):
        raise ValueError('请选择本地 MP4 / MOV / WebM / MKV / AVI / GIF 文件。')
    if sampling not in ('uniform','keyframes'):
        raise ValueError('取帧方式应为 uniform 或 keyframes。')
    if source.stat().st_size>2*1024**3:raise ValueError('源视频超过 2GB，请先裁成动作片段。')
    if count not in (0,8,16) or not 1<=fps<=30:
        raise ValueError('请选择全部源帧（0）、8 / 16 帧和 1–30 FPS。')
    all_frames=count==0
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'sequence.json').exists():
        raise ValueError('目标已有任务记录，请使用新目录，避免覆盖素材。')
    raw=folder/'source_frames';raw.mkdir()
    manifest={'schema_version':4,'kind':'walk','action':'custom','title':'导入视频动画帧',
        'method':'native_video_frames','status':'preparing','loop':bool(loop),'fps':fps,
        'frame_count':count,'frames':[],'source_video':str(source),'source_sha256':digest(source),
        'intent':{'action':'custom','direction':'source'},'frame_sampling':sampling,
        'post_color_rgb_preserved':True,'temporal_blending':False,'content_scaled':False,
        'all_source_frames':all_frames}
    save=lambda:write_json(folder/'sequence.json',manifest)
    save();started=time.monotonic()
    try:
        def check():
            if cancel.is_set():raise Cancelled('视频转帧已取消，已解码的原始帧保留。')
        with av.open(str(source)) as container:
            if not container.streams.video:raise ValueError('此文件没有视频画面。')
            stream=container.streams.video[0]
            duration=float(stream.duration*stream.time_base) if stream.duration else (
                container.duration/av.time_base if container.duration else None)
            if duration is None or not 0<duration<=30:
                raise ValueError('请选择有有效时长、且不超过 30 秒的动作片段；长视频请先裁剪。')
            if stream.width*stream.height>16_000_000:
                raise ValueError('视频尺寸超过当前转帧限制，请先裁剪到 1600 万像素以内。')
            if all_frames:
                fps=float(stream.average_rate or 24)
                if not 1<=fps<=30:raise ValueError('全部源帧导出目前支持1–30FPS，请选择均匀取帧。')
            sample_count=count*4+1
            sample_times=[i*duration/sample_count for i in range(sample_count)]
            sampled=[];timestamps=[];target=0
            origin=float(stream.start_time*stream.time_base) if stream.start_time is not None else None
            for ordinal,frame in enumerate(container.decode(stream)):
                check()
                timestamp=float(frame.time) if frame.time is not None else ordinal/float(stream.average_rate or 24)
                if origin is None:origin=timestamp
                timestamp-=origin
                if not all_frames and timestamp+1e-6<sample_times[target]:continue
                if all_frames and len(sampled)>=240:raise ValueError('全部源帧最多240张，请先裁短片段或选择8/16帧。')
                image=Image.fromarray(frame.to_ndarray(format='rgba'))
                path=raw/f'source_{len(sampled):04d}.png';image.save(path)
                sampled.append(path);timestamps.append(timestamp)
                emit('reference_stage',{'message':f'解码原生视频帧 {len(sampled)}…'})
                target+=1
                if not all_frames and target==sample_count:break
        if all_frames:
            count=len(sampled)
            if not count:raise ValueError('片段没有有效画面。')
            sampling='uniform'
            manifest.update(frame_count=count,fps=fps,frame_sampling='all_source_frames')
        if len(sampled)<count:raise ValueError('片段有效画面不足，请用更长的视频或减少输出帧数。')
        if all_frames:
            indices=list(range(count))
            selection={'method':'all_source_frames','source_indices':indices,'warnings':[]}
            if loop:selection['warnings'].append('保留全部源帧，未裁剪循环区间；循环播放仍需检查首尾接缝。')
        elif loop and len(sampled)>count:
            indices,selection=cycle_indices(sampled,count)
        else:
            indices=[round(i*(len(sampled)-1)/(count-1)) for i in range(count)]
            selection={'method':'uniform_real_frames','source_indices':indices,'warnings':[]}
            if loop:selection['warnings'].append('源帧数等于输出帧数，保留整段，请检查循环接缝。')
        if sampling=='keyframes':
            from .keyframe_capture import keyframe_indices
            start,end=(selection['start'],selection['endpoint']) if loop and 'start' in selection else (0,len(sampled))
            emit('reference_stage',{'message':'捕捉关键姿态，并从源动画补齐过渡帧…'})
            local,capture=keyframe_indices(sampled[start:end],count,timestamps[start:end])
            indices=[start+i for i in local]
            capture['key_source_indices']=[start+i for i in capture['key_source_indices']]
            capture['source_indices']=indices
            selection['keyframe_capture']=capture
            selection['source_indices']=indices
            selection['warnings'].extend(capture['warnings'])
        outputs=[];size=None
        for i,index in enumerate(indices):
            check()
            with Image.open(sampled[index]) as source_image:
                image=source_image.convert('RGBA')
                if transparent:
                    from .background import foreground_rgba
                    emit('reference_stage',{'message':f'生成后分离透明背景 · {i+1}/{count}…'})
                    original_rgb=image.convert('RGB').tobytes()
                    image=foreground_rgba(image,cancel,anti_alias=False)
                    if image.convert('RGB').tobytes()!=original_rgb:
                        raise ValueError('透明处理改变了 RGB，原始视频帧已保留。')
                if size is not None and image.size!=size:raise ValueError('源视频中途改变画布尺寸，请分段导入。')
                size=image.size
                target=folder/f'frame_{i:03d}.png';image.save(target);outputs.append(target)
            keyframe=index in selection.get('keyframe_capture',{}).get('key_source_indices',[])
            manifest['frames'].append({'index':i,'image':target.name,'source_frame':index,
                'source_time':timestamps[index],'stage':('关键姿态' if keyframe else '过渡帧') if sampling=='keyframes' else '视频动作',
                'phase':i/count,'is_keyframe':keyframe})
            emit('frame_ready',{'index':i,'count':count,'image':str(target)});save()
        from .walk_cycle import export_sequence
        manifest.update(status='completed',canvas=list(size),pose_selection=selection,
            exports=export_sequence(folder,outputs,fps,'custom',loop=loop),
            warnings=selection['warnings'],duration_seconds=round(time.monotonic()-started,2),
            source_duration=duration,source_times=timestamps)
        save()
        return {'manifest':str(folder/'sequence.json'),'frames':[str(p) for p in outputs],
            'warnings':selection['warnings']}
    except Exception as exc:
        manifest.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));save();raise
    finally:
        if transparent:
            from .background import release_session
            release_session()
