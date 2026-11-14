"""Official MiniMax H3 Image contract; independent of the shared video backend."""
import json
import math
from pathlib import Path
from .multi_reference import bind_text

MAX_IMAGES = 16
PROTOCOL = 'h3_image_native_v1'


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
