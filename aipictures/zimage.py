"""Z-Image Turbo text-to-image and image-to-image using the same installed weights."""
import math
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


def reference_available(info: dict) -> bool:
    return available(info) and all(n in info for n in ('LoadImage','ImageScale','VAEEncode'))


def prepare_reference(rgba, width: int, height: int):
    """Composite existing alpha and fit the requested canvas without stretching.

    This is model input preparation, not segmentation or sprite postprocessing.
    The original file is never changed. Output alpha is handled after inference.
    """
    from PIL import Image, ImageOps
    rgba=ImageOps.exif_transpose(rgba).convert('RGBA')
    rgb=Image.new('RGB',rgba.size,(242,243,245));rgb.paste(rgba,mask=rgba.getchannel('A'))
    return ImageOps.pad(rgb,(width,height),method=Image.Resampling.LANCZOS,color=(242,243,245))


def prompt_text(positive: str, negative: str) -> str:
    if not positive.strip():raise ValueError('请填写画面描述。')
    # Turbo's published CFG-1 path has no independent negative-conditioning pass.
    # Keep the user's exclusions as explicit natural-language soft constraints.
    return positive.strip()+('\n画面约束：避免出现以下内容：'+negative.strip() if negative.strip() else '')


def build(request: ImageRequest, info: dict, reference: str='', denoise: float=.45) -> tuple[dict,dict]:
    if request.lora:raise ValueError('Z-Image 不使用 SDXL 风格 LoRA，请切换 SDXL 或移除该选择。')
    if any(v<256 or v>2048 or v%16 for v in (request.width,request.height)):
        raise ValueError('Z-Image 画布应为 256–2048，且是 16 的倍数。')
    if not 0<=request.seed<2**64:raise ValueError('请使用有效的实际种子。')
    if reference and (not math.isfinite(denoise) or not .05<=denoise<=1.):
        raise ValueError('参考图重绘幅度应为0.05–1；越高越容易改变原图。')
    if reference and not reference_available(info):
        raise ValueError('Z-Image参考重绘缺少模型或LoadImage、ImageScale、VAEEncode节点，请刷新连接。')
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
    if reference:
        graph['reference']={'class_type':'LoadImage','inputs':{'image':reference}}
        # UI/CLI already fit and pad the RGB reference. Explicit dimensions also
        # make the saved API graph deterministic if replayed in ComfyUI.
        graph['reference_canvas']={'class_type':'ImageScale','inputs':{'image':['reference',0],
            'upscale_method':'lanczos','width':request.width,'height':request.height,'crop':'disabled'}}
        graph['latent']={'class_type':'VAEEncode','inputs':{'pixels':['reference_canvas',0],'vae':['vae',0]}}
        graph['sample']['inputs']['denoise']=float(denoise)
        graph['save']['inputs']['filename_prefix']='AIPictures/zimage_reference'
    if 'AIPicturesReleaseCompletedEncoders' in info:
        graph['release']={'class_type':'AIPicturesReleaseCompletedEncoders','inputs':{'model':['sampling',0],'conditioning':['text',0]}}
        graph['sample']['inputs']['model']=['release',0]
    return graph,{'positive':[('text','text')],'negative':[],'reference':['reference'] if reference else [],'sampler':'sample'}
