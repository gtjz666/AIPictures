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
    if image:
        graph['character']={'class_type':'LoadImage','inputs':{'image':image}}
        refs['ref_images.ref_image_0']=['character',0]
    return graph
