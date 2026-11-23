"""Official MiniMax H3 Image contract; independent of the shared video backend."""
import json
import math
import re
from pathlib import Path
from .multi_reference import bind_text, image_ids

MAX_IMAGES = 16
PROTOCOL = 'h3_image_native_v1'
EDIT_PROMPT_POLICY = 'native_reference_edit_v2'
UNSPECIFIED_REFERENCE = re.compile(r'另一(?:张|幅)(?:参考图|图片|图)?(?:的|里|中)|参考图(?:中|里|的)')
EDIT_PHRASE = r'(?:(?!图\d)[^，,。；;！!？?\n])'
TRANSFER_PATTERNS = (
    re.compile(rf'(?:请\s*)?(?:将|把|让|给)?\s*图(?P<base>\d+)(?P<before>{EDIT_PHRASE}{{0,80}}?)'
               r'(?:调整为|修改成|修改为|更换成|更换为|改成|改为|换成|换为|替换成|替换为|做出|作出|摆出|采用|模仿|复刻|使用|按照|照着)\s*'
               rf'图(?P<source>\d+)(?P<after>{EDIT_PHRASE}{{0,80}})'),
    re.compile(rf'(?:请\s*)?(?:保留|保持)\s*图(?P<base>\d+)(?P<before>{EDIT_PHRASE}{{1,80}})[，,；;]\s*'
               rf'(?:只|仅)?(?:采用|使用|模仿|复刻|参考|借用|换成)\s*图(?P<source>\d+)(?P<after>{EDIT_PHRASE}{{1,80}})'),
)
TRANSFER_ATTRIBUTES = {
    '动作姿势': r'动作|姿势|姿态|手势|站姿|坐姿|肢体',
    '面部表情': r'表情|神情|神态|视线',
    '面部外观': r'五官|脸型|面容|面貌|长相',
    '发型与发色': r'发型|发色|头发',
    '美术风格': r'美术风格|画风|风格|渲染风格',
    '服装配饰': r'衣服|服装|服饰|穿搭|配饰',
    '构图': r'构图|取景|机位|视角',
    '背景': r'背景|场景',
}


def settings(data):
    try:
        c=json.loads((Path(data)/'h3-image-settings.json').read_text('utf-8'))
        if not c.get('validated'):return {}
        if not Path(c['python']).is_file() or not (Path(c['source'])/'main.py').is_file():return {}
        if not Path(c['model_paths']).is_file():return {}
        if len(c['models'])!=2:return {}
        for row in c['models']+[c['encoder']]:
            if not row.get('sha256') or Path(row['path']).stat().st_size!=row['bytes']:return {}
        return c
    except (OSError,KeyError,TypeError,ValueError,AttributeError):return {}


def canvas(width,height):
    """Keep the base composition, around the official low-memory 4 MP template."""
    scale=math.sqrt(4_194_304/(width*height))
    w=max(256,round(width*scale/32)*32);h=max(256,round(height*scale/32)*32)
    return w,h


def validate(width,height,seed,references):
    if len(references)>MAX_IMAGES or any(not 1<=int(n)<=16 for n in references):raise ValueError('H3图片最多支持16张编号参考图。')
    if not 0<=seed<2**64:raise ValueError('种子范围应为0–2^64-1。')
    if min(width,height)<256 or max(width,height)>8192 or width%32 or height%32:raise ValueError('H3图片宽高须为256–8192之间的32倍数。')
    if not 1_000_000<=width*height<=20_000_000:raise ValueError('H3图片画幅须在100万–2000万像素之间；建议约400万像素。')


def instruction(text, references):
    if not text.strip() or len(text)>32000:raise ValueError('请填写32000字符以内的图片提示词。')
    # Slot numbers remain stable after deletion; compact exactly once for the model.
    return bind_text(text,list(references),label='Picture')


def simple_transfer(text):
    """Recognize clear source/target phrases. Leave compound edits to the model."""
    from .professional_prompt import labels
    text = labels(text).strip().rstrip('。.!！')
    for index, pattern in enumerate(TRANSFER_PATTERNS):
        match = pattern.fullmatch(text)
        if not match:
            continue
        base, source = int(match['base']), int(match['source'])
        before, after = match['before'], match['after']
        if base == source or re.search(r'不要|不改|排除|也要|保留|还要|同时|但是|并且', after):
            return None
        changed = after if index else before + ' ' + after
        attributes = [name for name, words in TRANSFER_ATTRIBUTES.items() if re.search(words, changed)]
        if not attributes and re.search(r'人物|角色|主体', before) and re.search(r'人物|角色|主体', after):
            attributes = ['指定主体的外观']
        if attributes:
            return base, source, attributes
    return None


def reference_edit(text, references):
    """Compile a numbered, native image edit from the user's own requirement."""
    manual = instruction(text, references)
    order = list(references)
    if len(order) < 2:
        return manual, order, None
    transfer = simple_transfer(text)
    if transfer:
        base, source, attributes = transfer
        order.remove(base)
        order.insert(0, base)
        fields = '、'.join(attributes)
        guide = (
            f'编辑图{base}并生成一张完整图片。图{base}是编辑底图；图{source}仅提供{fields}。\n'
            f'修改：仅将指定对象的{fields}改为图{source}中可见的对应特征。\n'
            f'保留：图{base}中未指定修改的属性、主体与画面关系。'
            f'成图中保留底图的主体数量，图{source}中的参考主体只用于借取指定属性。'
        )
        if '动作姿势' in attributes:
            guide += '按参考图迁移身体朝向、关节弯曲、手脚的位置及与身体或物体接触的位置。'
        if '面部表情' in attributes:
            guide += '按参考图迁移眼睛、眉毛和嘴部的状态。'
            if '面部外观' not in attributes:
                guide += '保留编辑对象的面部身份特征。'
        roles = dict(base_slot=base, source_slot=source, attributes=attributes)
    else:
        if len(image_ids(text)) < 2 and UNSPECIFIED_REFERENCE.search(text):
            raise ValueError('请说明改哪张图、另一张图用来做什么。例如：让图2的人物采用图1的动作和表情。')
        from .professional_prompt import labels
        base = re.match(r'(?:请\s*)?(?:编辑\s*图(\d+)|(?:编辑)?底图\s*[:：]\s*图(\d+)|以\s*图(\d+)\s*为(?:基底|底图|编辑基础))', labels(text).strip())
        roles = {}
        guide = ''
        if base:
            slot = int(next(number for number in base.groups() if number))
            order.remove(slot)
            order.insert(0, slot)
            roles['base_slot'] = slot
            guide = f'以图{slot}为编辑底图。'
        guide += (
            '根据用户要求生成一张完成图。分别确定要编辑的对象、各参考图提供的属性，以及应保留的部分。'
            '按图号从原图读取相关特征，每张图只用于用户指定的用途。'
            '保留编辑对象未要求改变的属性，按要求安排主体数量和画面关系。'
        )
    prompt = bind_text(f'{guide}\n用户要求（优先）：{text.strip()}', order, label='Picture')
    return prompt, order, dict(policy=EDIT_PROMPT_POLICY, model_order=order, **roles)


def reference_edit_canvas(references, roles, width, height):
    """Move an automatically fitted canvas with the identified editing image."""
    if not roles or 'base_slot' not in roles:
        return width, height
    first = next(iter(references))
    base = roles['base_slot']
    if first == base:
        return width, height
    from PIL import Image, ImageOps
    with Image.open(references[first]) as image:
        if (width, height) != canvas(*ImageOps.exif_transpose(image).size):
            return width, height
    with Image.open(references[base]) as image:
        return canvas(*ImageOps.exif_transpose(image).size)


def encode_graph(config,prompt,width,height,names,info=None):
    def name(node,field,path):
        if info:
            from .zimage import _name
            return _name(info,node,field,Path(path).name)
        return Path(path).name
    graph={f'image_{i}':dict(class_type='LoadImage',inputs=dict(image=n)) for i,n in enumerate(names,1)}
    graph.update(clip=dict(class_type='CLIPLoader',inputs=dict(clip_name=name('CLIPLoader','clip_name',config['encoder']['path']),type='minimax',device='default')),
        vae=vae(config,info),condition=dict(class_type='MiniMaxH3ImageConditioning',inputs=dict(clip=['clip',0],vae=['vae',0],prompt=prompt,width=width,height=height,
            **{f'images.image_{i}':[f'image_{i}',0] for i in range(1,len(names)+1)})),
        checkpoint=dict(class_type='AIPicturesSaveConditioning',inputs=dict(conditioning=['condition',0],latent=['condition',1])))
    return graph


def vae(config,info=None):
    name=Path(config['models'][1]['path']).name
    if info:
        from .zimage import _name
        name=_name(info,'VAELoader','vae_name',name)
    return dict(class_type='VAELoader',inputs=dict(vae_name=name))


def sample_graph(config,seed,info=None):
    name=Path(config['models'][0]['path']).name
    if info:
        from .zimage import _name
        name=_name(info,'UNETLoader','unet_name',name)
    return dict(condition=dict(class_type='AIPicturesLoadConditioning',inputs=dict(manifest='conditioning/conditioning.json')),
        model=dict(class_type='UNETLoader',inputs=dict(unet_name=name,weight_dtype='default')),
        negative=dict(class_type='ConditioningZeroOut',inputs=dict(conditioning=['condition',0])),
        sample=dict(class_type='KSampler',inputs=dict(model=['model',0],positive=['condition',0],negative=['negative',0],latent_image=['condition',1],
            seed=seed,steps=6,cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.)),
        checkpoint=dict(class_type='AIPicturesSaveConditioning',inputs=dict(conditioning=['condition',0],latent=['sample',0])))


def decode_graph(config,info=None):
    return dict(condition=dict(class_type='AIPicturesLoadConditioning',inputs=dict(manifest='conditioning/conditioning.json')),
        vae=vae(config,info),decode=dict(class_type='VAEDecode',inputs=dict(samples=['condition',1],vae=['vae',0])),
        save=dict(class_type='SaveImage',inputs=dict(images=['decode',0],filename_prefix='H3_Image')))
