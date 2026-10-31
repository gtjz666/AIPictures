"""User-described Wan I2V actions, without forced walking or human pose detection."""
import time
from pathlib import Path
from PIL import Image,ImageOps
from .animation_decode import sampling_workflow,decode_sampled
from .temporal_animation import video_workflow,initial_character_workflow,check_video_models
from .background import foreground_rgba,release_session
from .engine import Cancelled
from .engine_service import release_idle_models
from .storage import write_json
from .walk_cycle import SIZE,export_sequence
from .workflow_library import digest


def custom_prompt(description,appearance='',preserve=True):
    if not description.strip():raise ValueError('AI 自由动作需要填写动作说明。')
    text=('固定镜头，一个完整角色，保持参考图视角与角色比例，全身和肢体始终在画面内，简单浅灰色背景。'
          '动作要求：'+description.strip()+'。\n严格执行动作说明，避免用无关动作代替。'
          '整段保持相同的角色、服饰、发型、配色、光照与绘画风格，不添加额外肢体。')
    if not preserve and appearance.strip():text+='\n外观补充：'+appearance
    return text


def generate(client,folder,prompt,negative,seed,count,fps,emit,cancel,reference=None,checkpoint='',steps=20,
             custom_description='',lora='',lora_strength=.8,style_reference=False,preserve_reference=True,**_):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    if count not in (8,16):raise ValueError('自由动作支持 8 或 16 帧。')
    text=custom_prompt(custom_description,prompt,preserve_reference)
    manifest={'schema_version':4,'kind':'walk','action':'custom','title':'自定义 · AI 自由动作','method':'wan_i2v_custom',
        'status':'preparing','frame_count':count,'fps':fps,'canvas':list(SIZE),'seed':seed,'loop':False,'frames':[],
        'intent':{'action':'custom','direction':'reference'},'user_prompt':prompt,'custom_description':custom_description,
        'negative':negative,'timings':{},'style_reference':{'enabled':False},
        'quality_review':{'accepted':False,'warnings':['自由动作没有逐帧骨骼约束，复杂动作、接触和循环接缝需要人工验收。']}}
    save=lambda:write_json(folder/'sequence.json',manifest)
    save()
    try:
        check_video_models(client.discover()['object_info']);release_session();release_idle_models(client)
        if cancel.is_set():raise Cancelled('已取消自定义动作。')
        if reference is None:
            base=folder/'character';base.mkdir()
            graph=initial_character_workflow(prompt,negative,checkpoint,seed,20,lora,lora_strength)
            write_json(base/'workflow.json',graph)
            emit('workflow_ready',{'graph':graph,'url':client.url,'stage':'character'})
            result=client.generate(graph,base,lambda k,d:emit('character_event',{'event':k,'data':d}),cancel)
            write_json(base/'result.json',result);reference=result['images'][0];release_idle_models(client)
        elif style_reference:
            from .animation_style import restyle_reference
            reference,manifest['style_reference']=restyle_reference(client,reference,folder/'style-anchor',lora,
                lora_strength,checkpoint,seed,prompt,negative,emit,cancel)
        manifest.update(reference=str(reference),reference_sha256=digest(reference))
        # Only existing alpha is composited. No segmentation or color alteration before generation.
        with Image.open(reference) as source:
            rgba=source.convert('RGBA');back=Image.new('RGBA',rgba.size,'#e8e8e8');back.alpha_composite(rgba)
            image=ImageOps.pad(back.convert('RGB'),SIZE,Image.Resampling.LANCZOS,color='#e8e8e8')
            image.save(folder/'generation-reference.png')
        length=count*4+1;manifest['source_frame_count']=length
        graph=sampling_workflow(video_workflow(client.upload_image(folder/'generation-reference.png'),text,negative,
            seed,steps,length,size=SIZE))
        video=folder/'video';video.mkdir();write_json(video/'workflow.json',graph)
        manifest['status']='running';save()
        emit('workflow_ready',{'graph':graph,'url':client.url,'stage':'sampling'})
        emit('reference_stage',{'message':'按自定义说明生成自由动作；不强制走路或静态骨骼…'})
        sampled=client.generate(graph,video,lambda k,d:emit('pose_video_event',{'event':k,'data':d}),cancel,
            timeout=float('inf'),allow_latent_only=True,submitted=lambda pid:write_json(video/'submitted.json',{'prompt_id':pid}))
        write_json(video/'sampling_result.json',sampled);manifest['sampling_prompt_id']=sampled['prompt_id'];save()
        result=decode_sampled(client,sampled,video/'decode',emit,cancel)
        write_json(video/'result.json',result);release_idle_models(client)
        paths=result['images']
        if len(paths)!=length:raise ValueError('自由动作解码帧数不完整；原始数据保留，不会自动重提。')
        manifest['decode_prompt_id']=result['prompt_id'];manifest['prompt_id']=result['prompt_id']
        indices=[round(i*(length-1)/(count-1)) for i in range(count)];frames=[]
        for i,index in enumerate(indices):
            if cancel.is_set():raise Cancelled('已取消，已完成的原始帧保留。')
            emit('reference_stage',{'message':f'生成后分离透明背景 · {i+1}/{count}'})
            with Image.open(paths[index]) as source:
                rgb=source.convert('RGB');rgba=foreground_rgba(source,cancel,anti_alias=False)
                if rgba.size!=SIZE:raise ValueError('自由动作原生画布不一致，请检查解码输出。')
                if rgba.convert('RGB').tobytes()!=rgb.tobytes():raise ValueError('透明处理改变了 RGB，已保留原始帧。')
                target=folder/f'frame_{i:03d}.png';rgba.save(target);frames.append(target)
            manifest['frames'].append({'index':i,'image':target.name,'source_frame':index,'phase':i/(count-1),
                'stage':'自由动作','post_color_rgb_preserved':True})
            emit('frame_ready',{'index':i,'count':count,'image':str(target)});save()
        manifest.update(status='completed',exports=export_sequence(folder,frames,fps,'custom'),
            pose_selection={'method':'uniform_entire_sequence','source_indices':indices,'endpoint_duplicate_excluded':False})
        manifest['timings']['total_seconds']=round(time.monotonic()-started,3);save()
        return {'manifest':str(folder/'sequence.json'),'frames':[str(p) for p in frames],
                'gif':str(folder/'custom.gif'),'sprite_sheet':str(folder/'sprite_sheet.png'),
                'workflow':str(video/'workflow.json'),'warnings':manifest['quality_review']['warnings']}
    except Exception as exc:
        manifest.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));save();raise
    finally:
        release_session();release_idle_models(client)
