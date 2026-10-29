"""Real local inference acceptance cases. No GPU, RAM or temperature polling."""
import argparse
import json
import threading
import time
from pathlib import Path

from PIL import Image
from aipictures.engine import ComfyClient
from aipictures.general_image import reference_workflow
from aipictures.lora_catalog import catalog,style_prompt
from aipictures.prompt_binding import bind_request,check_models
from aipictures.storage import write_json
from aipictures.workflow import ImageRequest


def qwen_workflow(reference,prompt,negative='',seed=42,steps=40):
    graph={
        '1': {'class_type':'UNETLoader','inputs':{'unet_name':'qwen_image_edit_2511_fp8mixed.safetensors','weight_dtype':'default'}},
        '2': {'class_type':'CLIPLoader','inputs':{'clip_name':'qwen_2.5_vl_7b_fp8_scaled.safetensors','type':'qwen_image','device':'default'}},
        '3': {'class_type':'VAELoader','inputs':{'vae_name':'qwen_image_vae.safetensors'}},
        '4': {'class_type':'LoadImage','inputs':{'image':reference}},
        '5': {'class_type':'FluxKontextImageScale','inputs':{'image':['4',0]}},
        '6': {'class_type':'TextEncodeQwenImageEditPlus','inputs':{'clip':['2',0],'vae':['3',0],'image1':['5',0],'prompt':prompt}},
        '7': {'class_type':'TextEncodeQwenImageEditPlus','inputs':{'clip':['2',0],'vae':['3',0],'image1':['5',0],'prompt':negative}},
        '8': {'class_type':'ModelSamplingAuraFlow','inputs':{'model':['1',0],'shift':3.1}},
        '9': {'class_type':'CFGNorm','inputs':{'model':['8',0],'strength':1.}},
        '10': {'class_type':'VAEEncode','inputs':{'pixels':['5',0],'vae':['3',0]}},
        '11': {'class_type':'FluxKontextMultiReferenceLatentMethod','inputs':{'conditioning':['6',0],'reference_latents_method':'index_timestep_zero'}},
        '12': {'class_type':'FluxKontextMultiReferenceLatentMethod','inputs':{'conditioning':['7',0],'reference_latents_method':'index_timestep_zero'}},
        '13': {'class_type':'KSampler','inputs':{'model':['9',0],'positive':['11',0],'negative':['12',0],
            'latent_image':['10',0],'seed':seed,'steps':steps,'cfg':4.,'sampler_name':'euler','scheduler':'simple','denoise':1.}},
        '14': {'class_type':'VAEDecode','inputs':{'samples':['13',0],'vae':['3',0]}},
        '15': {'class_type':'SaveImage','inputs':{'images':['14',0],'filename_prefix':'AIPictures/research_general'}},
    }
    return graph


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8188')
    parser.add_argument('--kind',choices=['styles','qwen'],required=True)
    args=parser.parse_args();client=ComfyClient(args.url);root=Path('data/general-research')/args.kind;root.mkdir(parents=True,exist_ok=True)
    jobs=[];object_info=client.request('/object_info')
    if args.kind=='styles':
        for name in ('none','crayon','isometric'):
            entry=next((e for e in catalog() if e['id']==name),None)
            r=ImageRequest('sd_xl_base_1.0_0.9vae.safetensors','a small medieval shop building, stone walls, wooden roof, warm window lights, surrounded by trees, detailed game environment illustration',
                'blurry, watermark, text, people',768,768,30,6.5,20261029,'dpmpp_2m','karras',entry['filename'] if entry else '',entry['recommended_strength'] if entry else 0)
            r.positive,_=style_prompt(r.positive,r.lora)
            graph,_=bind_request(reference_workflow(r,''),r)
            jobs.append((name,graph))
    else:
        suite=json.loads(Path('data/reference-fill-research/suite.json').read_text('utf-8'))
        for case in suite['cases']:
            if case['id'] not in ('violet','yellow'): continue
            with Image.open(case['reference']) as src:
                image=src.convert('RGBA');bg=Image.new('RGBA',image.size,'#eeeeee');bg.alpha_composite(image)
                path=root/(case['id']+'-input.png');bg.convert('RGB').save(path)
            ref=client.upload_image(path)
            prompt=('将图中的角色改为正面全身视图，正对镜头，双脚完整入镜。保留同一个角色的身份、发型、服装、装饰和原有配色以及原始绘画风格，不能出现侧脸，不能增加道具，浅灰色纯色背景。' if case['id']=='violet' else
                '把图中的黄色卡通动物改为四分之三视角，抬起一只脚迈步。保留原来的物种、大眼睛、黄色身体、奶油色肚皮、尾巴、渐变阴影和柔和的绘画风格，保持完整身体，浅灰色背景。')
            jobs.append((case['id'],qwen_workflow(ref,prompt,'错误颜色，多余肢体，重影，文字，水印')))
    records=[]
    for name,graph in jobs:
        folder=root/name;folder.mkdir(exist_ok=True)
        if (folder/'result.json').is_file():
            print('Already completed:',name,flush=True);continue
        write_json(folder/'workflow.json',graph);start=time.monotonic()
        def event(kind,data):
            if kind=='queued':write_json(folder/'submitted.json',data)
            if kind in ('queued','executing','progress'): print(name,kind,data,flush=True)
        try:
            check_models(graph,object_info)
            result=client.generate(graph,folder,event,threading.Event(),timeout=float('inf'))
            result.update(elapsed_seconds=round(time.monotonic()-start,2),time_limit=None)
            write_json(folder/'result.json',result); records.append({'case':name,**result})
            print('Complete:',name,flush=True)
        except Exception as exc:
            write_json(folder/'error.json',{'error':str(exc),'elapsed_seconds':round(time.monotonic()-start,2)})
            print('Failed:',name,str(exc),flush=True)
    write_json(root/'results.json',records)


if __name__=='__main__': main()
