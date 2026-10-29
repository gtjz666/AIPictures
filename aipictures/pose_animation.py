"""Pose-sequence-conditioned Wan Animate, separate from free I2V and legacy skin warps."""
import json
import time
from copy import deepcopy
from pathlib import Path

from PIL import Image,ImageOps,ImageDraw

from .engine import Cancelled
from .engine_service import release_idle_models
from .motion_clip import ACTIONS,make_clip,sample_clip,paint_rig,validate_clip,body_pose
from .motion_reference import prepare_motion_reference
from .background import foreground_rgba,release_session
from .storage import write_json
from .temporal_animation import initial_character_workflow,ENCODER,VAE
from .walk_cycle import export_sequence,SIZE
from .workflow_library import digest
from .pose_condition import render_condition

MODEL='Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors'
SPEED_LORA='AIPictures/animation/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors'
VISION='CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'
VIDEO_SIZE=(480,640)


def animation_prompt(text,action='walk',preserve=True,negative=''):
    from .action_intent import appearance_description
    if action not in ACTIONS: raise ValueError('未知动画类型。')
    result=('一个完整主体，固定镜头，全身入镜，保持参考图朝向与视角，背景简洁。'+ACTIONS[action][1]+
        '严格按照连续骨骼图的每帧肢体姿态执行，从首帧就开始动作，不要先站立等待。'
        '每条腿只连接一只脚，每只鞋只有一个鞋跟、一个鞋尖和一层清晰鞋底；总共两只脚。'
        '脚部遵循所选动作与每帧骨骼，鞋面和鞋底轮廓清晰，不出现叠加鞋尖、分叉鞋底或额外脚掌。'
        '保持参考图的物种、五官、发型、发色、服装纹样、配饰、鞋型、身体比例与绘画风格。')
    result+='躯干随承重自然起伏，肩胯与摆臂协调，头部轻微缓冲，保持整段曝光、色温和配色一致。不添加参考图中没有的物品，不将姿态图彩色线条画成肤色或衣服。'
    result+='游戏逐帧动画，每帧都是清晰的瞬间定格；每只手和每条手臂只有一个明确轮廓，手臂运动连续但单帧边缘清晰，保留正常遮挡。'
    result+=' Crisp game sprite animation, sharp instantaneous poses, clean single contours on each limb and hand, fast shutter, consistent solid colors.'
    if not preserve:
        extra=appearance_description(text)
        if extra: result+='外观补充：'+extra
    result+=' Exactly two feet, one foot per leg, one heel and one toe per shoe, clean single soles. Follow the complete pose sequence.'
    if negative:
        from .animation_constraints import positive_restrictions
        result+='生成要求：'+positive_restrictions(negative)
    return result


def image_batch(graph,names,prefix='pose'):
    links=[]
    for index,name in enumerate(names):
        key=f'{prefix}_image_{index}'
        graph[key]={'class_type':'LoadImage','inputs':{'image':name}}
        links.append([key,0])
    level=0
    while len(links)>1:
        combined=[]
        for i in range(0,len(links),2):
            if i+1==len(links): combined.append(links[i]); continue
            key=f'{prefix}_batch_{level}_{i}'
            graph[key]={'class_type':'ImageBatch','inputs':{'image1':links[i],'image2':links[i+1]}}
            combined.append([key,0])
        links=combined; level+=1
    if not links: raise ValueError('缺少骨骼条件图。')
    return links[0]


def video_workflow(reference,poses,positive,negative,seed,steps=20,fast=False,face=None):
    n=len(poses)
    if n<5 or (n-1)%4: raise ValueError('骨骼视频帧数必须为 4n+1，且不少于 5 帧。')
    graph={
      '1':{'class_type':'UNETLoader','inputs':{'unet_name':MODEL,'weight_dtype':'default'}},
      '3':{'class_type':'CLIPLoader','inputs':{'clip_name':ENCODER,'type':'wan','device':'default'}},
      '4':{'class_type':'VAELoader','inputs':{'vae_name':VAE}},
      '5':{'class_type':'CLIPTextEncode','inputs':{'text':positive,'clip':['3',0]}},
      '6':{'class_type':'CLIPTextEncode','inputs':{'text':negative,'clip':['3',0]}},
      '7':{'class_type':'LoadImage','inputs':{'image':reference}},
      'vision':{'class_type':'CLIPVisionLoader','inputs':{'clip_name':VISION}},
      'vision_encode':{'class_type':'CLIPVisionEncode','inputs':{'clip_vision':['vision',0],'image':['7',0],'crop':'none'}},
      '9':{'class_type':'ModelSamplingSD3','inputs':{'model':['1',0],'shift':5.0}},
    }
    poses_link=image_batch(graph,poses)
    graph['8']={'class_type':'WanAnimateToVideo','inputs':{'positive':['5',0],'negative':['6',0],
        'vae':['4',0],'width':VIDEO_SIZE[0],'height':VIDEO_SIZE[1],'length':n,'batch_size':1,
        'reference_image':['7',0],'clip_vision_output':['vision_encode',0],'pose_video':poses_link,
        'continue_motion_max_frames':5,'video_frame_offset':0}}
    if face:
        graph['face']={'class_type':'LoadImage','inputs':{'image':face}}
        # One expression is intentionally held; feet and limb motion come from pose_video.
        graph['face_repeat']={'class_type':'RepeatImageBatch','inputs':{'image':['face',0],'amount':n}}
        graph['8']['inputs']['face_video']=['face_repeat',0]
    if fast:
        graph['acceleration']={'class_type':'LoraLoaderModelOnly','inputs':{'model':['1',0],
            'lora_name':SPEED_LORA,'strength_model':1.0}}
        graph['9']['inputs'].update(model=['acceleration',0],shift=8.0)
    graph['11']={'class_type':'KSampler','inputs':{'model':['9',0],'seed':seed,'steps':int(steps),
        'cfg':1.0,'sampler_name':'euler','scheduler':'simple','denoise':1.0,
        'positive':['8',0],'negative':['8',1],'latent_image':['8',2]}}
    graph['12']={'class_type':'TrimVideoLatent','inputs':{'samples':['11',0],'trim_amount':['8',3]}}
    graph['13']={'class_type':'VAEDecode','inputs':{'samples':['12',0],'vae':['4',0]}}
    graph['14']={'class_type':'SaveImage','inputs':{'images':['13',0],'filename_prefix':'AIPictures/pose_motion'}}
    graph['15']={'class_type':'SaveLatent','inputs':{'samples':['12',0],'filename_prefix':'AIPictures/pose_motion'}}
    return graph


def check_models(info,fast=False):
    graph=video_workflow('ref',['pose']*5,'move','',1,fast=fast)
    missing=sorted({node['class_type'] for node in graph.values()}-set(info))
    if missing: raise ValueError('动作骨骼缺少节点：'+', '.join(missing))
    for node,field,name in [('UNETLoader','unet_name',MODEL),('CLIPLoader','clip_name',ENCODER),
                            ('VAELoader','vae_name',VAE),('CLIPVisionLoader','clip_name',VISION)]:
        spec=info[node]['input']['required'][field]
        choices=spec[0] if isinstance(spec[0],list) else spec[1].get('options',[])
        if name not in choices: raise ValueError('动作骨骼缺少模型：'+name+'。安装后连接 / 刷新模型。')


def bind_model_names(graph,info):
    fields={'UNETLoader':'unet_name','CLIPVisionLoader':'clip_name','LoraLoaderModelOnly':'lora_name'}
    for node in graph.values():
        field=fields.get(node['class_type'])
        if not field: continue
        spec=info[node['class_type']]['input']['required'][field]
        choices=spec[0] if isinstance(spec[0],list) else spec[1].get('options',[])
        selected=node['inputs'][field].replace('\\','/')
        matched=next((name for name in choices if name.replace('\\','/')==selected),None)
        if matched is None: raise ValueError('模型未被引擎识别：'+selected)
        node['inputs'][field]=matched
    return graph


def export_frames(folder,result,manifest,clip,emit,cancel):
    from .reference_analysis import clean_foreground
    count=clip['frame_count']; length=manifest['source_frame_count']
    if len(result['images'])!=length: raise ValueError('生成帧数与骨骼序列不一致，原始结果已保留。')
    indices=[round(i*(length-1)/count) for i in range(count)]
    frames=[]; matte_paths=[]; poses=[]; matting_seconds=[]; started=time.monotonic()
    reference_rgba=None
    if manifest.get('preserve_reference',True) and (folder/'reference_analysis.json').is_file():
        analysis=json.loads((folder/'reference_analysis.json').read_text('utf-8'))
        with Image.open(analysis['rgba']) as source: reference_rgba=source.convert('RGBA')
    try:
        for i,index in enumerate(indices):
            if cancel.is_set(): raise Cancelled('动作透明处理已取消，原始帧已保留。')
            emit('reference_stage',{'message':f'处理{ACTIONS[clip["action"]][0]}透明帧 {i+1}/{count}'})
            frame_started=time.monotonic()
            with Image.open(result['images'][index]) as raw: image=foreground_rgba(raw,cancel,anti_alias=False)
            key=folder/f'frame_{i:03d}'; key.mkdir(exist_ok=True)
            # Separate pixel-asset source: no enlargement, palette repair or edge
            # smoothing. This route is consumed only on explicit pixel export.
            native=ImageOps.mirror(image) if manifest.get('source_direction')=='left' else image
            native.save(key/'matte_native.png')
            # A generated frame's fractional matte can contain motion trails.
            # Reference pinhole repair must not turn those trails into solid limbs.
            image=clean_foreground(image,repair_interior=False).resize(SIZE,Image.Resampling.LANCZOS)
            frame_pose=sample_clip(clip,i/count)
            matte_path=key/'matte.png'; image.save(matte_path); matte_paths.append(matte_path); poses.append(frame_pose)
            matting_seconds.append(round(time.monotonic()-frame_started,3))
            emit('matte_progress',{'value':i+1,'max':count})
            if (i+1)%4==0: release_session()
    finally: release_session()
    manifest.setdefault('timings',{}).update(matting_seconds=round(time.monotonic()-started,3),per_frame_matting_seconds=matting_seconds)
    emit('reference_stage',{'message':'检查并统一整段动画的亮度与偏色…'})
    from .sequence_color import plan_files,apply_correction
    color_started=time.monotonic(); color_plan=plan_files(matte_paths,poses)
    manifest['color_consistency']=color_plan; write_json(folder/'color-consistency.json',color_plan)
    palette=None
    if reference_rgba is not None:
        from .palette_consistency import palette_plan
        palette=palette_plan(matte_paths,poses,reference_rgba,clip['base_rig'])
        manifest['reference_palette']=palette;write_json(folder/'reference-palette-plan.json',palette)
    for i,(matte_path,frame_pose) in enumerate(zip(matte_paths,poses)):
        if cancel.is_set(): raise Cancelled('颜色处理已取消，原始透明帧已保留。')
        key=folder/f'frame_{i:03d}'; index=indices[i]
        with Image.open(matte_path) as matte: image=matte.convert('RGBA')
        if palette is not None:
            from .palette_consistency import apply_palette
            image,palette_quality=apply_palette(image,frame_pose,palette['frames'][i])
            if palette_quality['changed_pixels']:
                backup=key/'before_reference_palette.png'
                with Image.open(matte_path) as source: source.save(backup)
            write_json(key/'palette-quality.json',palette_quality)
        else:
            image=apply_correction(image,color_plan['frames'][i])
            palette_quality={'changed_pixels':0,'reason':'no_preserved_reference'}
        quality={'changed_pixels':0}
        if reference_rgba is not None:
            # Retain the narrow, previously validated hue guard as a fallback for
            # severe violet/blue hair casts; the general palette covers all colors.
            from .reference_color import repair_reference_hair
            corrected,hair_quality=repair_reference_hair(image,reference_rgba,frame_pose,clip['base_rig'])
            if hair_quality['changed_pixels']:
                image.save(key/'before_hair_color_repair.png');image=corrected
            write_json(key/'hair-quality.json',hair_quality)
            from .hand_quality import repair_reference_hands
            corrected,hand_quality=repair_reference_hands(image,reference_rgba,frame_pose,clip['base_rig'])
            if hand_quality['changed_pixels']:
                image.save(key/'before_hand_color_repair.png'); image=corrected
            write_json(key/'hand-quality.json',hand_quality)
            from .foot_quality import repair_light_footwear
            corrected,quality=repair_light_footwear(image,reference_rgba,frame_pose,clip['base_rig'])
            if quality['changed_pixels']:
                image.save(key/'matte_before_color_repair.png'); image=corrected
            write_json(key/'foot-quality.json',quality)
        else:
            hand_quality={'changed_pixels':0,'reason':'no_preserved_reference'}
            hair_quality={'changed_pixels':0,'reason':'no_preserved_reference'}
        # Keep the model's shared coordinates: per-frame grounding would erase a jump.
        output=folder/f'frame_{i:03d}.png'; image.save(output); frames.append(output)
        condition_pose=body_pose(frame_pose,clip['base_rig'])
        condition_image=render_condition(condition_pose,clip['base_rig'],SIZE)
        if manifest.get('source_direction')=='left':
            image=ImageOps.mirror(image); image.save(output)
            condition_image=ImageOps.mirror(condition_image)
            for rig in (frame_pose,condition_pose):
                for point in rig['joints'].values(): point[0]=767-point[0]
            frame_pose['direction']='left'
        write_json(key/'pose.json',frame_pose)
        condition_image.save(key/'pose.png')
        paint_rig(frame_pose,SIZE).save(key/'foot-controls.png')
        manifest['frames'].append({'index':i,'image':output.name,'source_frame':index,
            'native_matte':f'frame_{i:03d}/matte_native.png',
            'stage':ACTIONS[clip['action']][0],'phase':i/count,'pose':f'frame_{i:03d}/pose.json',
            'workflow':'video/workflow.json','prompt_id':result['prompt_id'],'foot_quality':quality,
            'color_consistency':color_plan['frames'][i],'hand_quality':hand_quality,'hair_quality':hair_quality,
            'reference_palette':palette_quality})
        # Magnified lower-leg review is saved separately so shoe topology is inspected.
        points=[frame_pose['joints'][side+'_'+part] for side in ('right','left') for part in ('ankle','heel','toe')]
        crop=image.crop((max(0,int(min(p[0] for p in points))-45),max(0,int(min(p[1] for p in points))-65),
            min(768,int(max(p[0] for p in points))+45),min(1024,int(max(p[1] for p in points))+25)))
        crop.save(key/'feet.png')
        write_json(folder/'sequence.json',manifest)
        emit('frame_ready',{'index':i,'count':count,'image':str(output)})
    manifest['timings']['color_and_frame_export_seconds']=round(time.monotonic()-color_started,3)
    emit('reference_stage',{'message':'保存精灵图与动画预览…'})
    export_started=time.monotonic()
    build_foot_review(folder,count)
    manifest.update(exports=export_sequence(folder,frames,clip['fps'],clip['action']),status='completed',
        pose_selection={'method':'entire_controlled_cycle','source_indices':indices,'endpoint_duplicate_excluded':True},
        quality_review={'feet':'foot-review.jpg','accepted':False,'note':'需逐帧检查足部结构；自动检查不证明生成准确率。'})
    write_json(folder/'sequence.json',manifest)
    manifest['timings']['sheet_and_gif_seconds']=round(time.monotonic()-export_started,3)
    write_json(folder/'sequence.json',manifest)
    return {'manifest':str(folder/'sequence.json'),'frames':[str(p) for p in frames],
        'workflow':str(folder/'video/workflow.json'),'gif':str(folder/(clip['action']+'.gif')),'sprite_sheet':str(folder/'sprite_sheet.png')}


def build_foot_review(folder,count):
    """A readable two-column close-up sheet, composed from actual exported pixels."""
    folder=Path(folder); sheet=Image.new('RGB',(720,math_ceil_half(count)*260),'white'); draw=ImageDraw.Draw(sheet)
    for index in range(count):
        with Image.open(folder/f'frame_{index:03d}/feet.png') as image:
            image=image.convert('RGBA'); image.thumbnail((350,225),Image.Resampling.LANCZOS)
            bg=Image.new('RGBA',image.size,'#f1f1f3'); painter=ImageDraw.Draw(bg)
            for y in range(0,image.height,12):
                for x in range(0,image.width,12):
                    if (x//12+y//12)%2: painter.rectangle((x,y,x+11,y+11),fill='#dadce0')
            bg=Image.alpha_composite(bg,image).convert('RGB')
            sheet.paste(bg,((index%2)*360+(360-bg.width)//2,(index//2)*260+25))
            draw.text(((index%2)*360+12,(index//2)*260+7),f'Frame {index+1}',fill='black')
    sheet.save(folder/'foot-review.jpg')


def math_ceil_half(value):
    return (value+1)//2


def generate(client,folder,prompt,negative,seed,count,fps,emit,cancel,reference=None,checkpoint='',steps=20,
             action='walk',motion=None,lora='',lora_strength=.8,static_test=False,fast=False,raw_only=False,preserve_reference=True,
             face_condition=False):
    folder=Path(folder)
    started=time.monotonic()
    manifest={'schema_version':4,'kind':'walk','action':action,'title':ACTIONS[action][0]+'动画',
        'method':'wan_animate_pose_sequence','status':'preparing','frames':[],'frame_count':count,'fps':fps,
        'canvas':list(SIZE),'seed':seed,'user_prompt':prompt,'negative':negative,'static_test':static_test,
        'preserve_reference':preserve_reference or reference is None,'timings':{}}
    save=lambda:write_json(folder/'sequence.json',manifest)
    save()
    try:
        if cancel.is_set(): raise Cancelled('已取消动作生成。')
        release_session(); manifest['initial_cache_release']=release_idle_models(client)
        if reference is None:
            from .background import process_result
            base=folder/'character'; base.mkdir()
            graph=initial_character_workflow(prompt,negative,checkpoint,seed,20,lora,lora_strength)
            write_json(base/'workflow.json',graph)
            result=client.generate(graph,base,lambda k,d:emit('character_event',{'event':k,'data':d}),cancel)
            manifest['character_cache_release']=release_idle_models(client)
            result=process_result(result,base,emit,cancel); write_json(base/'result.json',result)
            reference=result['images'][0]
        emit('reference_stage',{'message':'自动适配角色骨骼与脚部位置…'})
        analysis_started=time.monotonic()
        analysis=prepare_motion_reference(reference,client,emit,cancel)
        manifest['timings']['reference_analysis_seconds']=round(time.monotonic()-analysis_started,3)
        base=json.loads(Path(analysis['rig']).read_text('utf-8'))
        sha=digest(reference)
        if motion is not None:
            clip=validate_clip(deepcopy(motion))
            if clip['source_sha256']!=sha or clip['action']!=action or clip['frame_count']!=count:
                raise ValueError('手动骨骼与当前参考图、动作或帧数不匹配，请重新打开骨骼调整。')
            clip['fps']=fps
        else: clip=make_clip(base,sha,action,count,fps)
        write_json(folder/'motion.json',clip); write_json(folder/'reference_analysis.json',analysis)
        manifest.update(reference=str(reference),reference_sha256=sha,intent={'action':action,'direction':analysis['direction']},
            control='static_pose_test' if static_test else 'full_pose_sequence',source_direction=analysis['direction'])
        reference_name=client.upload_image(analysis['opaque'])
        face_name=None
        # Experimental diagnostic only: repeated-face conditioning has not passed
        # this machine's latency/visual acceptance and is not enabled by the UI.
        manifest['face_reference']={'used':False,'reason':'experimental_branch_disabled'}
        if face_condition and manifest['preserve_reference']:
            from .face_reference import reference_face
            with Image.open(analysis['opaque']) as source: face,face_report=reference_face(source,clip['base_rig'])
            manifest['face_reference']=face_report
            if face is not None:
                face_path=folder/'reference-face.png';face.save(face_path)
                face_name=client.upload_image(face_path,subfolder='AIPictures/reference_faces')
        # Exact cycle timing; no similarity heuristic may select only its first half.
        # Playback FPS changes playback only. It must not create hundreds of model frames.
        length=count*2+1
        pose_started=time.monotonic()
        pose_folder=folder/'poses'; pose_folder.mkdir(); names=[]
        for i in range(length):
            if cancel.is_set(): raise Cancelled('骨骼准备已取消。')
            pose=clip['base_rig'] if static_test else sample_clip(clip,i/(length-1))
            write_json(pose_folder/f'pose_{i:03d}.json',pose)
            path=pose_folder/f'pose_{i:03d}.png'
            render_condition(body_pose(pose,clip['base_rig']),clip['base_rig'],VIDEO_SIZE).save(path)
            names.append(client.upload_image(path,subfolder='AIPictures/poses'))
        manifest['timings']['pose_preparation_seconds']=round(time.monotonic()-pose_started,3)
        release_session(); manifest['pose_cache_release']=release_idle_models(client)
        video=folder/'video'; video.mkdir()
        effective_negative=negative+'，多余脚掌，重复鞋尖，分叉鞋底，双层鞋底，鞋子重影，断开的脚踝，姿态控制线条，额外色块，曝光突变，色温漂移'
        graph=video_workflow(reference_name,names,animation_prompt(prompt,action,preserve_reference,negative),effective_negative,seed,steps,fast,face=face_name)
        bind_model_names(graph,client.discover()['object_info'])
        write_json(video/'workflow.json',graph)
        manifest.update(status='running',source_frame_count=length,effective_negative=effective_negative,
            pose_format='wan_v2_body18_with_observed_hands_and_foot_derived_ankles',
            negative_policy='positive_constraints_with_cfg1_negative_recorded'); save()
        emit('workflow_ready',{'graph':graph,'url':client.url})
        inference_started=time.monotonic()
        result=client.generate(graph,video,lambda k,d:emit('pose_video_event',{'event':k,'data':d}),cancel,timeout=7200,
            submitted=lambda pid:write_json(video/'submitted.json',{'prompt_id':pid}))
        manifest['timings']['inference_wait_and_download_seconds']=round(time.monotonic()-inference_started,3)
        write_json(video/'result.json',result); manifest['video_cache_release']=release_idle_models(client)
        manifest['prompt_id']=result['prompt_id']
        if raw_only:
            manifest.update(status='completed_raw_test',raw_images=result['images']); save()
            return {'raw_images':result['images'],'manifest':str(folder/'sequence.json')}
        exports=export_frames(folder,result,manifest,clip,emit,cancel)
        manifest['timings']['total_seconds']=round(time.monotonic()-started,3); save()
        return exports
    except Exception as exc:
        manifest.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc)); save(); raise
    finally:
        release_session()
        # Cancellation/errors must also yield the large inference cache once idle.
        manifest['final_cache_release']=release_idle_models(client)
        try: save()
        except OSError: pass
