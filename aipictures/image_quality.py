"""Explicit optional restoration; default is light edge smoothing with no AI upscaler."""
from pathlib import Path
from PIL import Image,ImageFilter
import numpy as np

MODELS={'anime':'RealESRGAN_x4plus_anime_6B.pth','general':'RealESRGAN_x2plus.pth'}


def smooth_alpha(image):
    """Subpixel coverage on the silhouette only; retain interior RGB and true openings."""
    image=image.convert('RGBA'); alpha=image.getchannel('A')
    original=np.asarray(alpha)
    softened=np.asarray(alpha.filter(ImageFilter.GaussianBlur(.45)))
    # Limit smoothing to the one-pixel silhouette, keeping far background exactly zero.
    low=np.asarray(alpha.filter(ImageFilter.MinFilter(3)))
    high=np.asarray(alpha.filter(ImageFilter.MaxFilter(3)))
    band=(low<232)&(high>24)
    result=np.where(band,softened,original).astype(np.uint8)
    result[result<3]=0; result[result>252]=255
    output=image.copy(); output.putalpha(Image.fromarray(result)); return output


def check_quality_models(info,mode):
    if mode not in MODELS: return
    needed={'UpscaleModelLoader','ImageUpscaleWithModel','ImageScale'}
    if needed-set(info): raise ValueError('高清修复节点不齐全，请选择标准平滑，或安装 ComfyUI 放大节点。')
    spec=info['UpscaleModelLoader']['input']['required']['model_name']
    names=spec[0] if isinstance(spec[0],list) else spec[1].get('options',[])
    if MODELS[mode] not in names: raise ValueError('未安装高清修复模型：'+MODELS[mode])


def append_quality(graph,mode,width,height):
    if mode not in MODELS: return
    key='aipictures_quality_model'
    if any(name.startswith('aipictures_quality_') for name in graph):
        raise ValueError('工作流已经包含本软件高清修复节点，请关闭额外修复或在编辑器中配置。')
    outputs=[(name,node) for name,node in graph.items() if node['class_type']=='SaveImage']
    if not outputs: return
    graph[key]={'class_type':'UpscaleModelLoader','inputs':{'model_name':MODELS[mode]}}
    for index,(_,node) in enumerate(outputs):
        upscale=f'aipictures_quality_upscale_{index}'; resize=f'aipictures_quality_resize_{index}'
        graph[upscale]={'class_type':'ImageUpscaleWithModel','inputs':{'image':node['inputs']['images'],'upscale_model':[key,0]}}
        graph[resize]={'class_type':'ImageScale','inputs':{'image':[upscale,0],'upscale_method':'lanczos',
            'width':width,'height':height,'crop':'disabled'}}
        node['inputs']['images']=[resize,0]


def enhance_frames(client,paths,folder,mode,emit,cancel):
    """One optional, separately tracked API job after Wan releases its large caches."""
    folder=Path(folder); folder.mkdir(exist_ok=True)
    graph={}
    for index,path in enumerate(paths):
        if cancel.is_set():
            from .engine import Cancelled
            raise Cancelled('高清修复已取消')
        name=client.upload_image(path,subfolder='AIPictures/enhancement')
        graph[f'load_{index}']={'class_type':'LoadImage','inputs':{'image':name}}
        graph[f'save_{index}']={'class_type':'SaveImage','inputs':{'images':[f'load_{index}',0],
            'filename_prefix':f'AIPictures/quality_{index:03d}'}}
    append_quality(graph,mode,768,1024)
    from .storage import write_json
    write_json(folder/'workflow.json',graph)
    result=client.generate(graph,folder,lambda k,d:emit('quality_event',{'event':k,'data':d}),cancel,timeout=1800)
    # History preserves SaveImage node insertion order; map by node id for robust frame order.
    ordered=[]
    downloaded={}
    all_items=[]
    for output in result['history'].get('outputs',{}).values():
        all_items.extend(item for item in output.get('images',[]) if item.get('type','output')=='output')
    for item,path in zip(all_items,result['images']): downloaded[(item.get('subfolder',''),item['filename'])]=path
    for index in range(len(paths)):
        items=result['history']['outputs'][f'save_{index}']['images']
        item=next(item for item in items if item.get('type','output')=='output')
        ordered.append(downloaded[(item.get('subfolder',''),item['filename'])])
    result['images']=ordered; write_json(folder/'result.json',result)
    return result
