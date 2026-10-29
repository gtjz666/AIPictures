"""Native Wan2.2 temporal inference, independent of human keypoints and cutout rigs."""
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

from .action_intent import walk_intent, parse_intent, appearance_description
from .background import foreground_rgba, release_session, MODEL as MATTE_MODEL
from .engine import Cancelled
from .engine_service import release_idle_models
from .reference_analysis import clean_foreground
from .storage import write_json
from .walk_cycle import SIZE, export_sequence
from .workflow import ImageRequest, build_workflow
from .workflow_library import digest

HIGH = 'wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors'
LOW = 'wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors'
ENCODER = 'umt5_xxl_fp8_e4m3fn_scaled.safetensors'
VAE = 'wan_2.1_vae.safetensors'
VIDEO_SIZE = (576, 768)


def initial_character_workflow(prompt, negative, checkpoint, seed, steps=20,lora='',lora_strength=.8,quality_mode='off'):
    from .prompt_text import negative_text
    description=parse_intent(appearance_description(prompt)); intent=walk_intent(prompt)
    if not description.english.strip(): raise ValueError('请描述角色外观，例如：黄色卡通小恐龙，白色肚皮，大眼睛，全身，侧视。')
    species=re.search(r'\b(dinosaur|bird|penguin|duck|chick|cat|dog|rabbit)s?\b',description.english,re.I)
    animal=bool(species)
    clothing=any(word in prompt.lower() for word in ('衣','裙','裤','外套','夹克','制服','shirt','jacket','coat','pants','dress','uniform','outfit'))
    positive='one single full body character'
    extra_negative=''
    if animal and not clothing:
        positive='one single '+('cute small cartoon ' if '卡通' in prompt else '')+species[1].lower()
        extra_negative=', clothing, jacket, shirt, pants, trousers, dress, shoes, boots'
        colors={'黄色':'yellow','白色':'white','黑色':'black','粉色':'pink','蓝色':'blue','紫色':'purple','红色':'red','绿色':'green','橙色':'orange','棕色':'brown'}
        names='|'.join(colors)
        body=re.search(r'('+names+r')(?:的|卡通|可爱|圆润|Q版)*(?:小恐龙|恐龙|小鸟|企鹅|小鸭|小鸡|小猫|小狗|兔子)',prompt)
        if body:
            color=colors[body[1]]
            positive+=f', {color} skin, {color} head and face, {color} arms and legs, {color} back and tail'
        belly=re.search(r'('+names+r')(?:的)?(?:肚皮|腹部)',prompt)
        if belly: positive+=f', ({colors[belly[1]]} belly:1.25)'
        if '卡通' in prompt: positive+=', round head, big round eye, simple 2D cartoon, clean outlines, flat colors'
    appearance=description.english.replace('large eyes','one large visible eye')
    positive=f'(full side profile:1.35), facing {intent.direction}, '+positive
    positive+=', one visible eye, plain light gray background, '+appearance
    extra_negative+=', front view, three quarter view, looking at viewer'
    from .lora_catalog import style_prompt,validate_selection
    from .image_quality import append_quality
    validate_selection(lora,checkpoint); positive,_=style_prompt(positive,lora)
    request=ImageRequest(checkpoint,positive,negative_text(negative)[0]+extra_negative,768,1024,max(20,steps),6.0,seed,'dpmpp_2m','karras',lora,lora_strength)
    graph=build_workflow(request); append_quality(graph,quality_mode,768,1024)
    return graph


def animation_prompt(description,preserve_reference=False):
    intent = walk_intent(description)
    direction = '面朝'+('左' if intent.direction == 'left' else '右')+'方' if intent.direction_explicit and not preserve_reference else '保持参考图朝向'
    # Appearance prose may describe the standing input; the selected action is authoritative.
    view='保持参考图视角，全身' if preserve_reference else '全身侧视'
    text = (f'固定镜头，{view}，一个角色{direction}原地走路，完成自然的行走周期。'
        '左右腿交替迈步，前肢随步伐自然摆动，保持原图的肢体形状和数量。脚掌交替抬起与落地。'
        '保持参考图中主体的物种、身份、脸部、发型、服饰、颜色、身体比例和绘画风格。'
        '完整主体和脚部始终在画面内，位置和大小稳定，背景为简单浅灰色。')
    if intent.pace == 'slow': text += '缓慢行走，小步幅。'
    elif intent.pace == 'fast': text += '较快行走，自然步幅。'
    if preserve_reference:
        text+='参考图是外观的唯一依据，仅改变走路所需的肢体姿态；保留原有眼睛、五官、发丝、衣物纹样、配件、鞋面细节、线条和明暗，不添加新装饰，不重新设计角色。'
    appearance=appearance_description(description) if not preserve_reference else ''
    if appearance: text += '\n外观和细节补充：' + appearance
    text += ('\nFull body, same viewpoint as reference, ' if preserve_reference else '\nFull body side view, ')+\
        'the same single character walking in place, alternating steps, fixed camera, consistent appearance.'
    return text


def video_workflow(reference, prompt, negative, seed, steps=20, length=33):
    """Official non-distilled 14B settings: shift 5, CFG 3.5, Euler/simple, two experts."""
    if not reference: raise ValueError('14B 图生视频需要参考图；文字模式会先生成角色图。')
    steps = max(4, int(steps)); split = steps // 2
    graph = {
        '1': {'class_type':'UNETLoader','inputs':{'unet_name':HIGH,'weight_dtype':'default'}},
        '2': {'class_type':'UNETLoader','inputs':{'unet_name':LOW,'weight_dtype':'default'}},
        '3': {'class_type':'CLIPLoader','inputs':{'clip_name':ENCODER,'type':'wan','device':'default'}},
        '4': {'class_type':'VAELoader','inputs':{'vae_name':VAE}},
        '5': {'class_type':'CLIPTextEncode','inputs':{'text':prompt,'clip':['3',0]}},
        '6': {'class_type':'CLIPTextEncode','inputs':{'text':negative,'clip':['3',0]}},
        '7': {'class_type':'LoadImage','inputs':{'image':reference}},
        '8': {'class_type':'WanImageToVideo','inputs':{'positive':['5',0],'negative':['6',0],
            'vae':['4',0],'width':VIDEO_SIZE[0],'height':VIDEO_SIZE[1],'length':length,
            'batch_size':1,'start_image':['7',0]}},
        '9': {'class_type':'ModelSamplingSD3','inputs':{'model':['1',0],'shift':5.0}},
        '10': {'class_type':'ModelSamplingSD3','inputs':{'model':['2',0],'shift':5.0}},
        '11': {'class_type':'KSamplerAdvanced','inputs':{'model':['9',0], 'add_noise':'enable',
            'noise_seed':seed,'steps':steps,'cfg':3.5,'sampler_name':'euler','scheduler':'simple',
            'positive':['8',0],'negative':['8',1],'latent_image':['8',2],
            'start_at_step':0,'end_at_step':split,'return_with_leftover_noise':'enable'}},
        '12': {'class_type':'KSamplerAdvanced','inputs':{'model':['10',0], 'add_noise':'disable',
            'noise_seed':seed,'steps':steps,'cfg':3.5,'sampler_name':'euler','scheduler':'simple',
            'positive':['8',0],'negative':['8',1],'latent_image':['11',0],
            'start_at_step':split,'end_at_step':steps,'return_with_leftover_noise':'disable'}},
        '13': {'class_type':'VAEDecode','inputs':{'samples':['12',0],'vae':['4',0]}},
        '14': {'class_type':'SaveImage','inputs':{'images':['13',0],'filename_prefix':'AIPictures/temporal_walk'}},
        '15': {'class_type':'SaveLatent','inputs':{'samples':['12',0],'filename_prefix':'AIPictures/temporal_walk_latent'}},
    }
    return graph


def check_video_models(info):
    graph = video_workflow('__reference__', 'walk', '', 1)
    missing = sorted({node['class_type'] for node in graph.values()} - set(info))
    if missing: raise ValueError('连续动画缺少节点：' + ', '.join(missing))
    for node, field, filename in [('UNETLoader','unet_name',HIGH),('UNETLoader','unet_name',LOW),
                                  ('CLIPLoader','clip_name',ENCODER),('VAELoader','vae_name',VAE)]:
        choices = info[node]['input']['required'][field][0]
        if filename not in choices:
            raise ValueError('连续动画缺少模型：' + filename + '。安装后点击“连接 / 刷新模型”。')


def prepare_subject(reference, target, cancel, preserve_reference=False):
    """Use a mask for placement only; feed original colors/background to the model."""
    with Image.open(reference) as image: rgba = foreground_rgba(image, cancel)
    if not preserve_reference: rgba=clean_foreground(rgba)
    box = rgba.getchannel('A').point(lambda value: 255 if value > 24 else 0).getbbox()
    subject = rgba.crop(box)
    scale = min(900 / subject.height, 600 / subject.width)
    subject = subject.resize((max(1, round(subject.width * scale)), max(1, round(subject.height * scale))), Image.Resampling.LANCZOS)
    offset=((SIZE[0] - subject.width) // 2, 978 - subject.height)
    canvas = Image.new('RGBA', SIZE)
    canvas.paste(subject, offset)
    canvas.save(target.parent / 'reference_rgba.png')
    from .generation_reference import prepare_generation_reference
    geometry={'source_bbox':list(box),'scale':scale,'offset':list(offset),
        'subject_bbox':[offset[0],offset[1],offset[0]+subject.width,978]}
    preparation=prepare_generation_reference(reference,target,{'geometry':geometry,'direction':'right'})
    with Image.open(target) as image: conditioning=image.resize(VIDEO_SIZE,Image.Resampling.LANCZOS)
    conditioning.save(target)
    return {'source_bbox':list(box),'source_size':list(rgba.size),'scale':scale,
        'method':'source_pixels_no_human_pose','source_sha256':digest(reference),'generation_reference':preparation,
        'preserve_source_colors':True,'preserve_imported_alpha':preserve_reference,
        'conditioning_size':list(VIDEO_SIZE)}


def loop_indices(images, count):
    """Find a close temporal seam with motion, without assuming human poses or duplicating frames."""
    features = [np.asarray(image.resize((48,64)).convert('RGBA'),dtype=np.float32) / 255 for image in images]
    features = np.asarray(features)
    features[:,:,:,:3] *= features[:,:,:,3,None]
    best = None
    for start in range(min(9, len(images) - count)):
        for end in range(start + max(count, 12), len(images)):
            segment = features[start:end]
            motion = float(np.abs(segment - features[start]).mean())
            if motion < .002: continue
            seam = float(np.abs(features[start] - features[end]).mean())
            score = seam / max(.005, motion)
            if best is None or score < best[0]: best = (score, start, end)
    if best is None: best = (1., 0, len(images))
    _, start, end = best
    indices = [start + (i * (end - start)) // count for i in range(count)]
    return indices, {'start':start,'end_exclusive':end,'seam_to_motion_ratio':best[0],
                     'note':'选择较接近的首尾姿态；AI 输出仍需检查循环接缝和细节。'}


def stabilize_frames(images):
    """One shared scale, head/upper-body translation and ground alignment; never cut apart limbs."""
    boxes=[]; anchors=[]
    for image in images:
        alpha=np.asarray(image.getchannel('A')); ys,xs=np.nonzero(alpha>24)
        if not len(xs): raise ValueError('某一连续帧未分离出完整主体，原始视频帧已保留。')
        box=(int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)); boxes.append(box)
        upper=ys<box[1]+(box[3]-box[1])*.4
        anchors.append(float(np.median(xs[upper])))
    scale=min(900/max(box[3]-box[1] for box in boxes),600/max(box[2]-box[0] for box in boxes))
    anchor_target=384+float(np.median([(anchor-(box[0]+box[2])/2)*scale for anchor,box in zip(anchors,boxes)]))
    output=[]; offsets=[]
    for image,box,anchor in zip(images,boxes,anchors):
        x=float(np.clip(anchor_target-anchor*scale,24-box[0]*scale,744-box[2]*scale))
        y=978-box[3]*scale
        # PIL's RGBA transform handles the alpha interpolation with premultiplied colors.
        output.append(image.transform(SIZE,Image.Transform.AFFINE,(1/scale,0,-x/scale,0,1/scale,-y/scale),Image.Resampling.BICUBIC))
        offsets.append([x,y])
    return output,{'shared_scale':scale,'translation':offsets,'ground_y':978,'method':'whole_frame_only'}


def finish_sequence(folder,result,manifest,emit,cancel,enhance=None):
    """CPU-only transparent exports from saved native frames; no new GPU submission."""
    folder=Path(folder); count=manifest['frame_count']; fps=manifest['fps']
    def checked():
        if cancel.is_set(): raise Cancelled('透明帧处理已取消，原始连续帧已保留。')
    checked()
    if len(result['images'])<count: raise ValueError('视频工作流返回帧数不足，原始结果已保留。')
    # Framing/background are fixed by the video prompt. Select a temporal interval on
    # tiny RGB thumbnails first, so an 8-frame export does not segment 33-65 unused frames.
    thumbnails=[]
    for path in result['images']:
        checked()
        with Image.open(path) as image: thumbnails.append(image.resize((48,64)).convert('RGBA'))
    indices,manifest['loop_selection']=loop_indices(thumbnails,count)
    manifest['loop_selection']['measurement']='native_rgb_thumbnails_before_matting'
    selected=[result['images'][index] for index in indices]
    if enhance:
        quality=enhance(selected)
        manifest['quality']={'mode':manifest.get('quality_mode'),'images':quality['images'],
            'prompt_id':quality['prompt_id'],'source_indices':indices}
        selected=quality['images']
    elif manifest.get('quality'):
        quality=manifest['quality']
        if quality['source_indices']!=indices or any(not Path(path).is_file() for path in quality['images']):
            raise ValueError('缓存中的高清帧不匹配或已缺失，请重新生成；现有导出未修改。')
        selected=quality['images']
    mattes=[]
    try:
        for i,path in enumerate(selected):
            checked(); emit('reference_stage',{'message':f'处理动画帧透明背景 {i+1}/{count}…'})
            with Image.open(path) as image: matte=foreground_rgba(image,cancel,manifest.get('edge_smoothing',True))
            mattes.append(clean_foreground(matte,repair_interior=False))
            emit('matte_progress',{'value':i+1,'max':count})
            if (i+1)%4==0: release_session()
    finally: release_session()
    checked(); mattes,manifest['stabilization']=stabilize_frames(mattes)
    manifest['stabilization']['source_indices']=indices
    manifest['background']={'transparent':True,'model':MATTE_MODEL,'device':'cpu'}
    manifest.pop('matte_refinement',None)
    manifest.pop('matte_repair_policy',None)
    manifest['prompt_id']=result['prompt_id']; manifest['frames']=[]
    for i,index in enumerate(indices):
        checked(); output=folder/f'frame_{i:03d}.png'; mattes[i].save(output)
        manifest['frames'].append({'index':i,'image':output.name,'stage':f'连续行走 {i+1}/{count}',
            'source_frame':index,'workflow':'video/workflow.json','prompt_id':result['prompt_id'],'phase':i/count})
        write_json(folder/'sequence.json',manifest)
        emit('frame_ready',{'index':i,'count':count,'image':str(output)})
    checked(); manifest['exports']=export_sequence(folder,[folder/item['image'] for item in manifest['frames']],fps)
    manifest['status']='completed'; write_json(folder/'sequence.json',manifest)
    return {'manifest':str(folder/'sequence.json'),'frames':[str(folder/item['image']) for item in manifest['frames']],
        'workflow':str(folder/'video'/'workflow.json'),'gif':str(folder/'walk.gif'),'sprite_sheet':str(folder/'sprite_sheet.png')}


def generate_temporal(client, folder, prompt, negative, seed, count, fps, emit, cancel,
                      reference=None, checkpoint='', steps=20,lora='',lora_strength=.8,quality_mode='off',preserve_reference=True):
    folder = Path(folder)
    if count not in (8,16) or not 1 <= fps <= 30: raise ValueError('请选 8 / 16 帧，帧率 1–30。')
    preserve_reference=bool(reference) and preserve_reference
    if preserve_reference: quality_mode='off'
    intent = walk_intent(prompt)
    intent_data=intent.to_dict()
    if not intent.direction_explicit or preserve_reference: intent_data['direction']='reference'
    manifest = {'schema_version':3,'kind':'walk','status':'preparing','fps':fps,'frame_count':count,
        'canvas':list(SIZE),'ground_y':978,'seed':seed,'user_prompt':prompt,'negative':negative,
        'intent':intent_data,'reference':str(reference) if reference else None,
        'method':'wan22_14b_temporal_generation','frames':[],'preserve_reference':preserve_reference,
        'notes':'整段连续 AI 推理，不使用人体分层或逐帧复制肢体。透明遮罩由本地分割模型计算。'}
    from .lora_catalog import entry_for
    manifest.update(character_lora=lora if not reference else '',quality_mode=quality_mode,
        edge_smoothing=(entry_for(lora) or {}).get('quality')!='pixel' if not reference else True)
    save = lambda: write_json(folder/'sequence.json',manifest)
    save()
    def checked():
        if cancel.is_set(): raise Cancelled('连续动画已取消，已完成的结果保留在缓存。')
    try:
        checked()
        release_session()
        manifest['initial_cache_release']=release_idle_models(client)
        if not reference:
            emit('reference_stage',{'message':'先按文字描述生成角色参考图…'})
            graph = initial_character_workflow(prompt,negative,checkpoint,seed,steps,lora,lora_strength,quality_mode)
            base = folder/'character'; base.mkdir(exist_ok=True)
            write_json(base/'workflow.json',graph)
            result = client.generate(graph,base,lambda k,d:emit('character_event',{'event':k,'data':d}),cancel)
            manifest['character_cache_release']=release_idle_models(client)
            write_json(base/'result.json',result)
            reference = result['images'][0]; manifest['character_prompt_id']=result['prompt_id']
        checked(); emit('reference_stage',{'message':'准备参考主体；人物、卡通双足角色均不依赖人体关节识别…'})
        source = folder/'reference_rgb.png'
        manifest['reference_analysis'] = prepare_subject(reference,source,cancel,preserve_reference)
        manifest['reference_sha256'] = digest(reference)
        manifest['reference'] = str(reference)
        name = client.upload_image(source)
        release_session()
        # Two seconds at the model's native 16 FPS gives enough motion to select a loop.
        length = max(33, min(65, math.ceil(count / fps * 16 / 4) * 4 + 1))
        actual_negative=negative
        if preserve_reference:
            actual_negative+='，改变物种，改变身份，改变五官，改变发型，改变服装，改变纹样，改变配饰，改变配色，细节丢失，重新设计角色'
        manifest['effective_negative']=actual_negative
        graph = video_workflow(name,animation_prompt(prompt,preserve_reference),actual_negative,seed,steps,length)
        video = folder/'video'; video.mkdir(exist_ok=True); write_json(video/'workflow.json',graph)
        manifest['status']='running'; manifest['source_frame_count']=length; save()
        emit('reference_stage',{'message':'Wan2.2 14B 整段连续推理，首次加载可能较慢…'})
        result = client.generate(graph,video,lambda k,d:emit('video_event',{'event':k,'data':d}),cancel,timeout=7200,
            submitted=lambda pid:write_json(video/'submitted.json',{'prompt_id':pid}))
        write_json(video/'result.json',result); checked()
        emit('reference_stage',{'message':'连续推理完成，准备处理透明帧…'})
        manifest['video_cache_release']=release_idle_models(client)
        def enhance(paths):
            from .image_quality import enhance_frames
            enhanced=enhance_frames(client,paths,folder/'quality',quality_mode,emit,cancel)
            manifest['quality_cache_release']=release_idle_models(client)
            return enhanced
        return finish_sequence(folder,result,manifest,emit,cancel,enhance if quality_mode in ('anime','general') else None)
    except Exception as exc:
        manifest['status']='cancelled' if isinstance(exc,Cancelled) else 'failed'; manifest['error']=str(exc); save(); raise
    finally: release_session()
