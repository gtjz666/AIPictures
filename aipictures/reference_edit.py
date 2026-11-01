"""Native Chinese semantic reference editing using the already installed Qwen-Edit model."""
from .workflow import ImageRequest
import json
from pathlib import Path

MODEL='qwen_image_edit_2511_fp8mixed.safetensors'
ENCODER='qwen_2.5_vl_7b_fp8_scaled.safetensors'
VAE='qwen_image_vae.safetensors'


def enabled(info: dict,data: Path) -> bool:
    """A present checkpoint alone is not evidence of working local inference."""
    try:return available(info) and json.loads((Path(data)/'reference-edit-settings.json').read_text('utf-8')).get('validated') is True
    except (OSError,ValueError):return False


def available(info: dict) -> bool:
    needed=('TextEncodeQwenImageEditPlus','FluxKontextMultiReferenceLatentMethod','FluxKontextImageScale',
            'CFGNorm','EmptySD3LatentImage','ModelSamplingAuraFlow')
    if not all(name in info for name in needed):return False
    return all(file in info.get(node,{}).get('input',{}).get('required',{}).get(field,[[]])[0]
        for node,field,file in (('UNETLoader','unet_name',MODEL),('CLIPLoader','clip_name',ENCODER),('VAELoader','vae_name',VAE)))


def build(request: ImageRequest, reference: str, info: dict) -> tuple[dict,dict]:
    if not reference:raise ValueError('参考编辑需要先选择一张图片。')
    if not request.positive.strip():raise ValueError('请描述参考图中需要改变的内容。')
    if any(n<256 or n>2048 or n%16 for n in (request.width,request.height)):
        raise ValueError('参考编辑画布须为256–2048像素，且为16的整数倍。')
    prompt=('以参考图为基准，执行以下修改。保持未要求改变的主体身份、配色与细节。'
            '如果明确要求改变姿势、视角、背景或风格，应执行该变化，而非照抄原图。\n'+request.positive)
    graph={
        'model':{'class_type':'UNETLoader','inputs':{'unet_name':MODEL,'weight_dtype':'default'}},
        'clip':{'class_type':'CLIPLoader','inputs':{'clip_name':ENCODER,'type':'qwen_image','device':'default'}},
        'vae':{'class_type':'VAELoader','inputs':{'vae_name':VAE}},
        'reference':{'class_type':'LoadImage','inputs':{'image':reference}},
        'scale':{'class_type':'FluxKontextImageScale','inputs':{'image':['reference',0]}},
        'positive':{'class_type':'TextEncodeQwenImageEditPlus','inputs':{'clip':['clip',0],'vae':['vae',0],
            'image1':['scale',0],'prompt':prompt}},
        'negative':{'class_type':'TextEncodeQwenImageEditPlus','inputs':{'clip':['clip',0],'vae':['vae',0],
            'image1':['scale',0],'prompt':request.negative}},
        'pos_ref':{'class_type':'FluxKontextMultiReferenceLatentMethod','inputs':{'conditioning':['positive',0],'reference_latents_method':'index_timestep_zero'}},
        'neg_ref':{'class_type':'FluxKontextMultiReferenceLatentMethod','inputs':{'conditioning':['negative',0],'reference_latents_method':'index_timestep_zero'}},
        'latent':{'class_type':'EmptySD3LatentImage','inputs':{'width':request.width,'height':request.height,'batch_size':1}},
        'shift':{'class_type':'ModelSamplingAuraFlow','inputs':{'model':['model',0],'shift':3.1}},
        'norm':{'class_type':'CFGNorm','inputs':{'model':['shift',0],'strength':1.}},
        'sample':{'class_type':'KSampler','inputs':{'model':['norm',0],'positive':['pos_ref',0],'negative':['neg_ref',0],
            'latent_image':['latent',0],'seed':request.seed,'steps':40,'cfg':4.,'sampler_name':'euler','scheduler':'simple','denoise':1.}},
        'decode':{'class_type':'VAEDecode','inputs':{'samples':['sample',0],'vae':['vae',0]}},
        'save':{'class_type':'SaveImage','inputs':{'images':['decode',0],'filename_prefix':'AIPictures/reference_edit'}}}
    if 'AIPicturesReleaseCompletedEncoders' in info:
        graph['ready']={'class_type':'ConditioningCombine','inputs':{'conditioning_1':['pos_ref',0],'conditioning_2':['neg_ref',0]}}
        graph['release']={'class_type':'AIPicturesReleaseCompletedEncoders','inputs':{'model':['norm',0],'conditioning':['ready',0]}}
        graph['sample']['inputs']['model']=['release',0]
    return graph,{'positive':[('positive','prompt')],'negative':[('negative','prompt')],'reference':['reference'],'sampler':'sample'}
