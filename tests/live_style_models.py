"""Controlled real ComfyUI runs: same prompt/seed, LoRA zero vs selected strength."""
import json
import argparse
import math
import threading
import time
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from aipictures.engine import ComfyClient
from aipictures.workflow import ImageRequest,build_workflow
from aipictures.prompt_binding import bind_request
from aipictures.lora_catalog import catalog,entry_for,style_prompt
from aipictures.storage import DATA,write_json


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--only',nargs='+',choices=[v['id'] for v in catalog()])
    args=parser.parse_args(); entries=[v for v in catalog() if not args.only or v['id'] in args.only]
    client=ComfyClient(); info=client.discover()
    root=DATA/'style-model-tests'/datetime.now().strftime('%Y%m%d_%H%M%S'); root.mkdir(parents=True)
    checkpoint=next(n for n in info['checkpoints'] if 'sd_xl_base' in n)
    sheet=Image.new('RGB',(1024,math.ceil(len(entries)/2)*344),'white'); draw=ImageDraw.Draw(sheet)
    records=[]; started=time.monotonic()
    prompt='portrait of an adult woman with short dark blue hair, white blouse, neutral expression, plain light gray background, clean composition'
    for position,entry in enumerate(entries):
        name=next(n for n in info['loras'] if entry_for(n) and entry_for(n)['id']==entry['id'])
        positive,_=style_prompt(prompt,name); images=[]; pair=[]
        for variant,strength in [('off',0),('on',entry['recommended_strength'])]:
            folder=root/(entry['id']+'-'+variant); folder.mkdir()
            request=ImageRequest(checkpoint,positive,'blurry, watermark, text, extra limbs, deformed face',512,640,16,6,20261028,'dpmpp_2m','karras',name,strength)
            graph,_=bind_request(build_workflow(request),request)
            write_json(folder/'workflow.json',graph); state={'progress':0}
            def event(kind,data):
                if kind=='progress': state['progress']+=1
            result=client.generate(graph,folder,event,threading.Event())
            assert state['progress']>0
            write_json(folder/'result.json',result)
            with Image.open(result['images'][0]) as image: images.append(image.convert('RGB').copy())
            pair.append({'variant':variant,'strength':strength,'prompt_id':result['prompt_id'],'progress_events':state['progress']})
            col=(position%2)*2+(variant=='on'); row=position//2
            sheet.paste(images[-1].resize((256,320)),(col*256,row*344+24))
            draw.text((col*256+6,row*344+6),entry['id']+' '+variant,fill='black')
        delta=float(np.abs(np.asarray(images[0],dtype=float)-np.asarray(images[1],dtype=float)).mean())
        assert delta>.05,(entry['id'],delta)
        records.append({'id':entry['id'],'filename':name,'category':entry['category'],'mean_rgb_difference':delta,'runs':pair})
        sheet.save(root/'comparison.jpg'); print(entry['id'],'verified; mean RGB delta',round(delta,2),flush=True)
    record={'passed':True,'folder':str(root),'models':records,'same_prompt_and_seed_per_pair':True,
        'lora_selected_explicitly':True,'automatic_lora_selection':False,'elapsed_seconds':round(time.monotonic()-started,1),
        'note':'验证实际加载与输出变化；样图仍需人工检查，不代表所有提示词质量。'}
    write_json(root/'acceptance.json',record)
    write_json(DATA/('style-refinement-acceptance.json' if args.only else 'style-models-acceptance.json'),record)
    print(f'{len(records)} style LoRAs changed real inference output.',flush=True)


if __name__=='__main__': main()
