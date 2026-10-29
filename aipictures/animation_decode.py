"""Separate heavy sampling from native VAE decoding; preserve the saved latent."""
from copy import deepcopy
from pathlib import Path

from .engine import Cancelled
from .engine_service import release_idle_models
from .storage import write_json
from .workflow_library import digest


def sampling_workflow(graph):
    result=deepcopy(graph)
    if result.get('15',{}).get('class_type')!='SaveLatent':
        raise ValueError('动画采样必须先保存潜变量，不能安全拆分此工作流。')
    result.pop('13',None);result.pop('14',None)
    return result


def decode_workflow(latent,vae_name='wan_2.1_vae.safetensors'):
    return {'load':{'class_type':'LoadLatent','inputs':{'latent':latent}},
        'vae':{'class_type':'VAELoader','inputs':{'vae_name':vae_name}},
        'decode':{'class_type':'VAEDecode','inputs':{'samples':['load',0],'vae':['vae',0]}},
        'save':{'class_type':'SaveImage','inputs':{'images':['decode',0],'filename_prefix':'AIPictures/pose_motion'}}}


def decode_sampled(client,sampled,folder,emit,cancel,vae_name='wan_2.1_vae.safetensors'):
    folder=Path(folder)
    if cancel.is_set():raise Cancelled('解码已取消，已完成的生成数据保留。')
    latents=sampled.get('latents',[])
    if len(latents)!=1 or not Path(latents[0]).is_file():
        raise ValueError('动画采样缺少唯一有效的潜变量文件；原始任务记录保留，不会自动重新生成。')
    if (folder/'submitted.json').exists():
        raise ValueError('该目录已有解码任务，请先查看任务记录，避免重复提交。')
    folder.mkdir(parents=True,exist_ok=True)
    cleanup=release_idle_models(client)
    emit('reference_stage',{'message':'动作采样已保存，释放大模型后解码原生帧…'})
    # The shared Comfy upload endpoint stores opaque bytes, including .latent;
    # LoadLatent validates the uploaded path and reads safetensors on the backend.
    name=client.upload_image(latents[0],subfolder='AIPictures/latents')
    graph=decode_workflow(name,vae_name)
    write_json(folder/'source.json',{'sampling_prompt_id':sampled['prompt_id'],'latent':latents[0],
        'latent_sha256':digest(latents[0]),'resampled':False,'cache_cleanup':cleanup})
    write_json(folder/'workflow.json',graph)
    emit('workflow_ready',{'graph':graph,'url':client.url,'stage':'decode'})
    result=client.generate(graph,folder,lambda k,d:emit('decode_event',{'event':k,'data':d}),cancel,
        timeout=float('inf'),submitted=lambda pid:write_json(folder/'submitted.json',{'prompt_id':pid}))
    write_json(folder/'result.json',result)
    return dict(result,latents=latents,sampling_prompt_id=sampled['prompt_id'],decode_prompt_id=result['prompt_id'],
        image_workflow=str(folder/'workflow.json'))
