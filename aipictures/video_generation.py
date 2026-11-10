"""Prompt/reference -> complete animation. Matting and sprites follow explicit export."""
import time
import math
from pathlib import Path
from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest


def compose_prompt(appearance: str, action: str, reference: bool) -> str:
    if not action.strip():raise ValueError('请描述角色需要完成的动作。')
    parts=['主体与场景外观：'+appearance.strip()] if appearance.strip() else []
    parts.append('优先执行的动作要求：'+action.strip())
    parts.append('如果外观描述中含有冲突的动作，只执行本次动作要求，不叠加不同姿势。')
    if reference:
        parts.append('以参考图作为主体身份、衣着、配色和画风基准；仅修改文字明确要求改变的部分。允许完成动作所需的转身、关节和视角变化。')
    parts.append('完整主体始终在画面内，固定镜头，不切镜、不突然缩放。动作连贯，肢体数量与主体一致，保持稳定的配色、细节、光照与背景。')
    return '\n'.join(parts)


def generation_prompt(params: dict,reference: bool) -> str:
    if params.get('prompt_layout')!='unified':
        return compose_prompt(params['prompt'],params.get('action_description',''),reference)
    text=params['prompt'].strip()
    if not text:raise ValueError('请在正向提示词中描述画面与动作。')
    if reference:text+='\n以参考图保留未要求改变的主体身份、衣着、配色和画风，执行文字明确要求的动作与变化。'
    if params.get('creation_kind')=='short_video':return text
    return text+'\n完整主体保持在画面内，动作连贯，配色与细节稳定，不切镜、不突然缩放。'


def generate(client, folder: Path, params: dict, cancel, emit) -> dict:
    folder=Path(folder);started=time.monotonic()
    manifest={'schema_version':1,'kind':'video','status':'preparing','params':params,
        'title':'自由动画','frames':[],'sprites_created':False,'matting_before_generation':False}
    save=lambda:write_json(folder/'video.json',manifest)
    save()
    try:
        if params.get('creation_kind')=='short_video':
            from .video_script import validate
            validate(params.get('short_script'),params['seconds'])
        if params['engine']=='h3':
            if params['seconds']>8 or params.get('resume_chain'):
                from .video_chain import generate as h3_generate
            elif params.get('motion_reference'):
                from .motion_native_backend import generate as h3_generate
            else:
                from .h3_backend import generate as h3_generate
            result=h3_generate(folder,params,cancel,emit)
            source=Path(result['video']) if result.get('video') else None
            from .video_io import preview_frames,native_rgb_frames,encode_pngs
            if result.get('native_frames'):
                paths=[Path(p) for p in result['native_frames']];fps=24
                manifest.update(native_rgb_preserved=result.get('native_rgb_preserved',True),native_frame_sha256=result['frame_sha256'],warnings=result.get('warnings',[]))
            elif result.get('native_rgb'):
                fps=24
                if params.get('defer_exports'):
                    from .video_io import native_rgb_info
                    count,_,_=native_rgb_info(Path(result['native_rgb']))
                    paths=[];manifest.update(native_rgb_source=str(Path(result['native_rgb']).resolve()),
                                            frame_count=count,frame_storage='native_rgb')
                else:
                    paths=native_rgb_frames(Path(result['native_rgb']),folder/'preview_frames',cancel,emit)
                    result['delivery_video']=str(source)
                    source=folder/'animation_master.mp4';encode_pngs(paths,source,fps,cancel)
                manifest.update(native_rgb_preserved=True,native_rgb_sha256=digest(Path(result['native_rgb'])))
            else:
                paths,fps=preview_frames(source,folder/'preview_frames',cancel,emit)
                manifest.update(native_rgb_preserved=False,warnings=['缺少原生RGB数据，预览使用交付视频解码；可能有视频压缩误差。'])
        else:
            raise ValueError('旧 Wan 动画工作流已停用；请使用 MiniMax H3。历史动画仍可预览与选帧导出。')
        count=len(paths) or manifest.get('frame_count',0)
        if params.get('defer_exports'):
            requested=math.ceil(params['seconds']*fps)
            kept=min(count,requested)
            manifest.update(model_frame_count=count,alignment_tail_frames=count-kept,video_export_pending=True)
            paths=paths[:kept];count=kept
            if 'native_frame_sha256' in manifest:manifest['native_frame_sha256']=manifest['native_frame_sha256'][:kept]
        if params.get('creation_kind')=='short_video':
            from .video_io import encode_native_rgb
            emit('video_stage',dict(message='画面已完成，正在制作配乐并合成音画…'))
            silent=folder/'video_silent.mp4'
            if result.get('native_rgb'):encode_native_rgb(Path(result['native_rgb']),silent,round(fps),cancel,emit,frame_count=count)
            else:encode_pngs(paths,silent,round(fps),cancel)
            from .video_audio import package
            tracks=package(folder,source,count/fps,params,cancel);source=Path(tracks['video'])
            manifest.update(**{k:v for k,v in tracks.items() if k!='video'},video_export_pending=False,
                            short_script=params.get('short_script'),title='短视频（含配乐）')
        manifest.update(status='completed',source_video=str(source.resolve()) if source else None,source_sha256=digest(source) if source else None,
            frames=[{'image':str(p.resolve().relative_to(folder.resolve()))} for p in paths],fps=fps,
            frame_count=count,duration_seconds=count/fps,elapsed_seconds=round(time.monotonic()-started,2),
            source_result=result)
        save();return {'manifest':str(folder/'video.json'),'video':str(source) if source else None,'frames':[str(p) for p in paths]}
    except Exception as exc:
        manifest.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));save();raise
