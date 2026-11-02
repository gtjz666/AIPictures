"""Prompt/reference -> complete animation. Matting and sprites follow explicit export."""
import json
import time
from pathlib import Path
from dataclasses import asdict

from PIL import Image,ImageOps

from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest
from .engine_service import release_idle_models


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
    return text+'\n完整主体保持在画面内，动作连贯，配色与细节稳定，不切镜、不突然缩放。'


def generate(client, folder: Path, params: dict, cancel, emit) -> dict:
    folder=Path(folder);started=time.monotonic()
    manifest={'schema_version':1,'kind':'video','status':'preparing','params':params,
        'title':'自由动画','frames':[],'sprites_created':False,'matting_before_generation':False}
    save=lambda:write_json(folder/'video.json',manifest)
    save()
    try:
        if params['engine']=='h3':
            from .h3_backend import generate as h3_generate
            result=h3_generate(folder,params,cancel,emit)
            source=Path(result['video'])
            from .video_io import preview_frames,native_rgb_frames,encode_pngs
            if result.get('native_rgb'):
                paths=native_rgb_frames(Path(result['native_rgb']),folder/'preview_frames',cancel,emit);fps=24
                result['delivery_video']=str(source)
                source=folder/'animation_master.mp4';encode_pngs(paths,source,fps,cancel)
                manifest.update(native_rgb_preserved=True,native_rgb_sha256=digest(Path(result['native_rgb'])))
            else:
                paths,fps=preview_frames(source,folder/'preview_frames',cancel,emit)
                manifest.update(native_rgb_preserved=False,warnings=['缺少原生RGB数据，预览使用交付视频解码；可能有视频压缩误差。'])
        else:
            from .temporal_animation import video_workflow,check_video_models
            from .animation_decode import sampling_workflow,decode_sampled
            from .workflow import ImageRequest,build_workflow
            from . import zimage
            info=client.discover();reference=params.get('reference')
            check_video_models(info['object_info'])
            queue=client.request('/queue')
            if queue.get('queue_running') or queue.get('queue_pending'):
                emit('video_stage',{'message':'等待共享引擎执行动画…'})
            if not reference:
                emit('video_stage',{'message':'按画面描述生成角色基准，不使用骨骼或 LoRA…'})
                prompt=params['prompt'].strip()
                if params.get('prompt_layout')=='unified':prompt='根据以下描述制作动画的起始画面，只画一个时间点，不画序列图：\n'+prompt
                if not prompt:raise ValueError('无参考图时请填写画面或角色描述。')
                request=ImageRequest(params['checkpoint'],prompt,params['negative'],768,1024,30,5.5,params['seed'],'dpmpp_2m','karras')
                if zimage.available(info['object_info']):
                    graph,_=zimage.build(request,info['object_info'])
                else:
                    from .general_image import positive_text
                    request.positive=positive_text(prompt)[0];graph=build_workflow(request)
                base=folder/'anchor';base.mkdir();write_json(base/'workflow.json',graph)
                emit('workflow_ready',{'graph':graph,'url':client.url,'stage':'anchor'})
                created=client.generate(graph,base,emit,cancel);write_json(base/'result.json',created)
                reference=created['images'][0];release_idle_models(client)
            if cancel.is_set():raise Cancelled('动画已取消。')
            with Image.open(reference) as image:
                rgba=ImageOps.exif_transpose(image).convert('RGBA')
                back=Image.new('RGBA',rgba.size,'#e8e8e8');back.alpha_composite(rgba)
                prepared=ImageOps.pad(back.convert('RGB'),(768,1024),Image.Resampling.LANCZOS,color='#e8e8e8')
                prepared.save(folder/'reference_rgb.png')
            fps=16;length=4*round(params['seconds']*fps/4)+1
            graph=sampling_workflow(video_workflow(client.upload_image(folder/'reference_rgb.png'),
                generation_prompt(params,True),params['negative'],
                params['seed'],params['steps'],length,size=(768,1024)))
            if 'AIPicturesWanImageToVideo' in info['object_info']:graph['8']['class_type']='AIPicturesWanImageToVideo'
            sampling=folder/'sampling';sampling.mkdir();write_json(sampling/'workflow.json',graph)
            emit('workflow_ready',{'graph':graph,'url':client.url,'stage':'sampling'})
            emit('video_stage',{'message':'生成完整动画片段；尚未拆帧或去背景…'})
            sampled=client.generate(graph,sampling,emit,cancel,allow_latent_only=True)
            write_json(sampling/'result.json',sampled);save()
            decoded=decode_sampled(client,sampled,folder/'decode',emit,cancel)
            paths=[Path(p) for p in decoded['images']]
            if len(paths)!=length:raise ValueError('完整片段帧数不符，潜变量与已完成画面保留。')
            from .video_io import encode_pngs
            source=folder/'animation.mp4'
            emit('video_stage',{'message':'保存完整动画，准备预览…'})
            encode_pngs(paths,source,fps,cancel)
            result={'sampling_prompt_id':sampled['prompt_id'],'video':str(source)}
            release_idle_models(client)
        manifest.update(status='completed',source_video=str(source.resolve()),source_sha256=digest(source),
            frames=[{'image':str(p.resolve().relative_to(folder.resolve()))} for p in paths],fps=fps,
            frame_count=len(paths),duration_seconds=len(paths)/fps,elapsed_seconds=round(time.monotonic()-started,2),
            source_result=result)
        save();return {'manifest':str(folder/'video.json'),'video':str(source),'frames':[str(p) for p in paths]}
    except Exception as exc:
        manifest.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));save();raise
