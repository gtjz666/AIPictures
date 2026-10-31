"""Restyle an anchor with a compatible SDXL LoRA before Wan animates it."""
from pathlib import Path
from .workflow import ImageRequest
from .general_image import reference_workflow,positive_text
from .lora_catalog import validate_selection,style_prompt,is_sdxl
from .prompt_text import negative_text
from .storage import write_json
from .workflow_library import digest
from .engine_service import release_idle_models


def style_workflow(reference,checkpoint,lora,strength,seed,prompt='',negative=''):
    if not lora:raise ValueError('启用动画换风格后，请在“采样与 LoRA”中手动选择风格。')
    if not is_sdxl(checkpoint):raise ValueError('动画风格重绘需要 SDXL 基础模型与对应 LoRA，请在“模型与画面”中选择 SDXL。')
    validate_selection(lora,checkpoint)
    text='one single character, same silhouette, same pose, full body, plain light gray background, '+positive_text(prompt)[0]
    text,_=style_prompt(text,lora)
    request=ImageRequest(checkpoint,text,negative_text(negative)[0],768,1024,28,6.,seed,'dpmpp_2m','karras',lora,strength)
    graph=reference_workflow(request,reference,.5)
    graph['style_scale']={'class_type':'ImageScale','inputs':{'image':['reference',0],'upscale_method':'lanczos',
        'width':768,'height':1024,'crop':'disabled'}}
    graph['style_encode']={'class_type':'VAEEncode','inputs':{'pixels':['style_scale',0],'vae':['1',2]}}
    graph['5']['inputs'].update(latent_image=['style_encode',0],denoise=.62)
    graph.pop('4');return graph


def restyle_reference(client,reference,folder,lora,strength,checkpoint,seed,prompt,negative,emit,cancel):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    from PIL import Image,ImageOps
    # Composite existing transparency only. Do not segment or discard source RGB before inference.
    with Image.open(reference) as source:
        rgba=source.convert('RGBA');back=Image.new('RGBA',rgba.size,'#e8e8e8');back.alpha_composite(rgba)
        ImageOps.pad(back.convert('RGB'),(768,1024),Image.Resampling.LANCZOS,color='#e8e8e8').save(folder/'source_rgb.png')
    graph=style_workflow(client.upload_image(folder/'source_rgb.png'),checkpoint,lora,strength,seed,prompt,negative)
    from .prompt_binding import check_models
    check_models(graph,client.discover()['object_info'])
    write_json(folder/'workflow.json',graph)
    emit('reference_stage',{'message':'按主动选择的 LoRA 重绘角色风格，再生成动作…'})
    emit('workflow_ready',{'graph':graph,'url':client.url,'stage':'style_anchor'})
    result=client.generate(graph,folder,lambda k,d:emit('character_event',{'event':k,'data':d}),cancel)
    write_json(folder/'result.json',result);release_idle_models(client)
    output=result['images'][0]
    record={'enabled':True,'method':'sdxl_styled_anchor_then_wan','lora':lora,'strength':strength,
            'checkpoint':checkpoint,'original_reference':str(reference),'original_sha256':digest(reference),
            'styled_reference':output,'styled_sha256':digest(output),'prompt_id':result['prompt_id']}
    write_json(folder/'style.json',record);return output,record
