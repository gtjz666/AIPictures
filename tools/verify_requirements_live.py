"""Explicit local assistant and one FLUX edit acceptance; never retries old jobs."""
import argparse
import json
import threading
from pathlib import Path
from aipictures.professional_prompt import organize
from aipictures.sfx_prompt import organize as sfx
from aipictures.engine import ComfyClient
from aipictures.motion_native_backend import release_shared
from aipictures.workflow import ImageRequest
from aipictures.flux_klein import build,UNET
from aipictures.storage import write_json


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);args=parser.parse_args()
    root=args.proof.resolve();root.mkdir(parents=True,exist_ok=False);cancel=threading.Event()
    config=json.loads((args.data/'local-intent-settings.json').read_text('utf-8'));client=ComfyClient('http://127.0.0.1:8188')
    release_shared(dict(url=client.url),cancel=cancel)
    job=json.loads((args.data/'jobs/20261110_222345_d42c04da/job.json').read_text('utf-8'))
    references=job['params']['references'];reference=Path(references[-1]['source'])
    edit=organize(config,'将图1的人物改为双手抱头，保留人物外形','',{1:reference},None,root/'image-text',cancel,lambda *_:None)
    assert not edit['images_read'] and edit['plan']['negative_prompt']==''
    refs={row['number']:Path(row['source']) for row in references}
    style=organize(config,'将图1的人物美术风格修改为图2的美术风格，保留图1的人物动作与人物外形','',refs,None,root/'style-text',cancel,lambda *_:None)
    action='仅保留人物外形，先反复抱头惊叹，然后捧腹大笑，最后躺在地上反复大笑打滚'
    animated=organize(config,action,'',{},None,root/'animation-text',cancel,lambda *_:None,selected_kind='animation',output_seconds=6)
    assert action in animated['plan']['positive_prompt'] and not animated['plan']['timeline']
    sound=sfx(config,'两次清脆的金属刀剑碰撞，然后短促回响，不要音乐',5,root/'sfx-text',cancel,lambda *_:None)
    info=client.request('/object_info');uploaded=client.upload_image(reference)
    req=ImageRequest(UNET,edit['english']['positive'],'',512,768,4,1.,20261111,'euler','flux2')
    graph,_=build(req,info,uploaded);render=root/'image';render.mkdir()
    write_json(render/'workflow.json',graph);write_json(render/'requirement.json',dict(source='将图1的人物改为双手抱头，保留人物外形',compiled=edit['english'],reference=str(reference)))
    result=client.generate(graph,render,lambda kind,data:print(kind,flush=True) if kind in ('queued','completed') else None,cancel)
    write_json(root/'acceptance.json',dict(image=result,raw_motion_order_retained=True,no_image_analysis=True,source_style_direction=style['english'],sfx=sound))
    release_shared(dict(url=client.url),cancel=cancel)
    print('Live text contracts and one FLUX edit completed',flush=True)


if __name__=='__main__':main()
