"""Official dedicated Ref2VA conditioning, native base sampler, lossless RGB output."""
from .zimage import _name

MODEL='minimax_h3_ref2va_pruned_int8_convrot.safetensors'
ENCODER='qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'
VAE='minimax_h3_video_vae_int8_convrot.safetensors'


def build(info,prompt,seed,width,height,length,manifest,image=''):
    required=('MiniMaxH3ReferenceToVideo','AIPicturesMotionFrames','BasicGuider','BasicScheduler','SamplerCustomAdvanced')
    if any(n not in info for n in required):raise ValueError('专用H3参考后端节点不完整，请检查独立环境。')
    refs=dict(clip=['clip',0],vae=['vae',0],prompt=prompt,width=width,height=height,length=length,
              ref_image_size='match',**{'ref_videos.ref_video_0':['motion',0]})
    graph={
        'model':{'class_type':'UNETLoader','inputs':{'unet_name':_name(info,'UNETLoader','unet_name',MODEL),'weight_dtype':'default'}},
        'clip':{'class_type':'CLIPLoader','inputs':{'clip_name':_name(info,'CLIPLoader','clip_name',ENCODER),'type':'minimax','device':'default'}},
        'vae':{'class_type':'VAELoader','inputs':{'vae_name':_name(info,'VAELoader','vae_name',VAE)}},
        'motion':{'class_type':'AIPicturesMotionFrames','inputs':{'manifest':manifest}},
        'references':{'class_type':'MiniMaxH3ReferenceToVideo','inputs':refs},
        'noise':{'class_type':'RandomNoise','inputs':{'noise_seed':seed}},
        'sampler':{'class_type':'KSamplerSelect','inputs':{'sampler_name':'res_multistep'}},
        'sigmas':{'class_type':'BasicScheduler','inputs':{'model':['model',0],'scheduler':'simple','steps':20,'denoise':1.}},
        'guider':{'class_type':'BasicGuider','inputs':{'model':['model',0],'conditioning':['references',0]}},
        'sample':{'class_type':'SamplerCustomAdvanced','inputs':{'noise':['noise',0],'guider':['guider',0],'sampler':['sampler',0],
                    'sigmas':['sigmas',0],'latent_image':['references',1]}},
        'decode':{'class_type':'VAEDecode','inputs':{'samples':['sample',0],'vae':['vae',0]}},
        'save':{'class_type':'SaveImage','inputs':{'images':['decode',0],'filename_prefix':'AIPictures/reference_motion'}}}
    images=list(image) if isinstance(image,(list,tuple)) else [image] if image else []
    if len(images)>4:raise ValueError('视频编辑一次最多4张参考图。')
    for i,path in enumerate(images):
        key='character' if i==0 else f'reference_{i+1}'
        graph[key]={'class_type':'LoadImage','inputs':{'image':path}}
        refs[f'ref_images.ref_image_{i}']=[key,0]
    return graph


def encoding(info,prompt,seed,width,height,length,manifest,image=''):
    if 'AIPicturesSaveConditioning' not in info:raise ValueError('专用后端缺少分阶段条件保存节点，请更新私有节点。')
    full=build(info,prompt,seed,width,height,length,manifest,image)
    graph={k:v for k,v in full.items() if k in ('clip','vae','motion','references','character') or k.startswith('reference_')}
    graph['checkpoint']={'class_type':'AIPicturesSaveConditioning','inputs':{'conditioning':['references',0],'latent':['references',1]}}
    return graph


def sampling(info,seed,width,height,length):
    if 'AIPicturesLoadConditioning' not in info:raise ValueError('专用后端缺少分阶段条件读取节点，请更新私有节点。')
    full=build(info,'',seed,width,height,length,'')
    graph={k:v for k,v in full.items() if k not in ('clip','motion','references')}
    graph['references']={'class_type':'AIPicturesLoadConditioning','inputs':{'manifest':'conditioning/conditioning.json'}}
    return graph


def anchor_continuation(graph:dict,info:dict,image:str)->None:
    """Official H3 guide at frame zero, preserving Ref2VA text/visual blocks."""
    if 'MiniMaxH3AddGuide' not in info:raise ValueError('参考后端缺少官方H3首帧引导节点，不能续接。')
    graph['continuation']={'class_type':'LoadImage','inputs':{'image':image}}
    graph['anchor']={'class_type':'MiniMaxH3AddGuide','inputs':{'positive':['references',0],
        'latent':['references',1],'vae':['vae',0],'image':['continuation',0],'frame_idx':0}}
    graph['checkpoint']['inputs']['conditioning']=['anchor',0]
