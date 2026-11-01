"""Official Z-Image Turbo topology; native Chinese, no SDXL LoRA or reference mixing."""
from .workflow import ImageRequest

UNET='z_image_turbo_bf16.safetensors'
ENCODER='qwen_3_4b_fp8_mixed.safetensors'
VAE='ae.safetensors'


def _name(info: dict, node: str, field: str, filename: str) -> str:
    spec=info.get(node,{}).get('input',{}).get('required',{}).get(field)
    names=spec[0] if spec and isinstance(spec[0],list) else []
    match=next((name for name in names if name.replace('\\','/').split('/')[-1]==filename),None)
    if match is None:raise ValueError('Z-Image 组件尚未安装或后端未刷新：'+filename)
    return match


def available(info: dict) -> bool:
    try:
        for node,field,file in (('UNETLoader','unet_name',UNET),('CLIPLoader','clip_name',ENCODER),('VAELoader','vae_name',VAE)):
            _name(info,node,field,file)
        return all(n in info for n in ('EmptySD3LatentImage','ModelSamplingAuraFlow','ConditioningZeroOut'))
    except ValueError:return False


def prompt_text(positive: str, negative: str) -> str:
    if not positive.strip():raise ValueError('请填写画面描述。')
    # Turbo's published CFG-1 path has no independent negative-conditioning pass.
    # Keep the user's exclusions as explicit natural-language soft constraints.
    return positive.strip()+('\n画面约束：避免出现以下内容：'+negative.strip() if negative.strip() else '')


def build(request: ImageRequest, info: dict) -> tuple[dict,dict]:
    if request.lora:raise ValueError('Z-Image 不使用 SDXL 风格 LoRA，请切换 SDXL 或移除该选择。')
    if any(v<256 or v>2048 or v%16 for v in (request.width,request.height)):
        raise ValueError('Z-Image 画布应为 256–2048，且是 16 的倍数。')
    text=prompt_text(request.positive,request.negative)
    graph={
        'unet':{'class_type':'UNETLoader','inputs':{'unet_name':_name(info,'UNETLoader','unet_name',UNET),'weight_dtype':'default'}},
        'clip':{'class_type':'CLIPLoader','inputs':{'clip_name':_name(info,'CLIPLoader','clip_name',ENCODER),'type':'lumina2','device':'default'}},
        'vae':{'class_type':'VAELoader','inputs':{'vae_name':_name(info,'VAELoader','vae_name',VAE)}},
        'text':{'class_type':'CLIPTextEncode','inputs':{'text':text,'clip':['clip',0]}},
        'negative':{'class_type':'ConditioningZeroOut','inputs':{'conditioning':['text',0]}},
        'latent':{'class_type':'EmptySD3LatentImage','inputs':{'width':request.width,'height':request.height,'batch_size':1}},
        'sampling':{'class_type':'ModelSamplingAuraFlow','inputs':{'model':['unet',0],'shift':3.}},
        'sample':{'class_type':'KSampler','inputs':{'model':['sampling',0],'positive':['text',0],'negative':['negative',0],
            'latent_image':['latent',0],'seed':request.seed,'steps':9,'cfg':1.,'sampler_name':'euler','scheduler':'simple','denoise':1.}},
        'decode':{'class_type':'VAEDecode','inputs':{'samples':['sample',0],'vae':['vae',0]}},
        'save':{'class_type':'SaveImage','inputs':{'images':['decode',0],'filename_prefix':'AIPictures/zimage'}}}
    if 'AIPicturesReleaseCompletedEncoders' in info:
        graph['release']={'class_type':'AIPicturesReleaseCompletedEncoders','inputs':{'model':['sampling',0],'conditioning':['text',0]}}
        graph['sample']['inputs']['model']=['release',0]
    return graph,{'positive':[('text','text')],'negative':[],'reference':[],'sampler':'sample'}
