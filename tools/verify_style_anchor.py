"""Real local SDXL style-anchor check. Refuses to compete with an occupied shared queue."""
import argparse
import threading
import time
from pathlib import Path
from PIL import Image
from aipictures.animation_style import restyle_reference
from aipictures.backend_connection import shared_backend_url
from aipictures.engine import ComfyClient
from aipictures.workflow_library import digest
from aipictures.storage import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--lora',default='AIPictures/ghibli-sdxl.safetensors')
    parser.add_argument('--strength',type=float,default=.8)
    parser.add_argument('--checkpoint',default='sd_xl_base_1.0_0.9vae.safetensors')
    args=parser.parse_args()
    if args.out.exists():parser.error('输出目录已经存在，请使用新目录，避免重复提交。')
    client=ComfyClient(shared_backend_url('http://127.0.0.1:8188'));queue=client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):parser.error('共享引擎正在执行任务，请等现有任务完成。')
    original=digest(args.reference);started=time.monotonic()
    def emit(kind,data):
        if kind=='reference_stage' or kind=='character_event' and data['event'] in ('queued','progress','executing'):
            print(kind,data,flush=True)
    output,record=restyle_reference(client,args.reference,args.out,args.lora,args.strength,args.checkpoint,20261030,
        '保持同一个角色，紫色盘发，白色无袖衬衫，黑色短裤，黑色长袜，棕色鞋，全身侧视',
        '模糊，重影，多余肢体，裁切，文字',emit,threading.Event())
    with Image.open(output) as image:size=list(image.size)
    record.update(source_unchanged=digest(args.reference)==original,canvas=size,
        elapsed_seconds=round(time.monotonic()-started,2),actual_generation=True,
        functional_execution_passed=size==[768,1024] and digest(output)!=original,
        animation_visual_review='not measured by this anchor-only check')
    write_json(args.out/'acceptance.json',record);print(record,flush=True)


if __name__=='__main__':main()
