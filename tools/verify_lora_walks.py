"""Serial, real SDXL-LoRA anchor -> Wan walk comparisons using the production pipeline."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from aipictures.backend_connection import shared_backend_url
from aipictures.engine import ComfyClient
from aipictures.lora_catalog import catalog
from aipictures.pose_animation import generate,check_models
from aipictures.storage import write_json
from aipictures.workflow_library import digest
from tools.verify_animation_modes import inspect_exports

APPEARANCE=('same adult woman as the reference, dark purple hair in a low bun, green eyes, '
    'white sleeveless blouse, black bow necktie, black high-waisted shorts, black thigh-high stockings, '
    'brown loafers, full body, right-facing side view, retain character identity and outfit')
NEGATIVE='duplicate character, extra limbs, extra feet, ghosting, blurry outlines, missing colors, text, watermark, cropped head, cropped feet'


def one_case(args):
    entries={entry['id']:entry for entry in catalog()};entry=entries[args.one]
    folder=args.out/args.one
    if folder.exists():
        if (folder/'acceptance.json').is_file():
            saved=json.loads((folder/'acceptance.json').read_text('utf-8'))
            sequence=json.loads((folder/'sequence.json').read_text('utf-8'))
            if (saved.get('functional_execution_passed') and saved.get('original_sha256')==digest(args.reference)
                    and sequence.get('seed')==args.seed and saved.get('lora')==entry['filename']
                    and saved.get('strength')==entry['recommended_strength']):return
            raise ValueError('已有结果未通过或参数不同，请使用新的输出目录：'+str(folder))
        raise ValueError('该目录已有未完成任务，请检查原任务记录，不能重复提交：'+str(folder))
    client=ComfyClient(shared_backend_url(args.url));check_models(client.discover()['object_info'])
    cancel=threading.Event()
    while True:
        q=client.request('/queue')
        if not q.get('queue_running') and not q.get('queue_pending'):break
        print(json.dumps({'style':args.one,'state':'waiting_for_shared_queue'}),flush=True);cancel.wait(10)
    folder.mkdir(parents=True)
    original_sha=digest(args.reference);started=time.monotonic()
    def emit(kind,data):
        if kind in ('reference_stage','frame_ready') or kind in ('character_event','pose_video_event','decode_event') and data['event'] in (
                'queued','progress','executing','monitor_waiting','cancel_pending'):
            print(json.dumps({'style':args.one,'kind':kind,'data':data},ensure_ascii=True),flush=True)
    generate(client,folder,APPEARANCE,NEGATIVE,args.seed,8,8,emit,cancel,args.reference,
        checkpoint='sd_xl_base_1.0_0.9vae.safetensors',steps=20,action='walk',lora=entry['filename'],
        lora_strength=entry['recommended_strength'],preserve_reference=True,detail='native',sampler='euler',
        color_mode='original',style_reference=True)
    record=inspect_exports(folder);manifest=json.loads((folder/'sequence.json').read_text('utf-8'))
    record.update(style_id=args.one,title=entry['title'],lora=entry['filename'],strength=entry['recommended_strength'],
        original_sha256=original_sha,original_reference_unchanged=digest(args.reference)==original_sha,
        styled_anchor=manifest['style_reference'],elapsed_seconds=round(time.monotonic()-started,2),
        source_reference=str(args.reference.resolve()),seed=args.seed)
    write_json(folder/'acceptance.json',record)
    print(json.dumps(record,ensure_ascii=True),flush=True)
    if not record['functional_execution_passed']:raise RuntimeError('导出验收失败，请查看 acceptance.json。')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--styles',nargs='+',default=['ghibli','watercolor','render-3d'])
    p.add_argument('--one',choices=[e['id'] for e in catalog()]);p.add_argument('--seed',type=int,default=20261030)
    p.add_argument('--url',default='http://127.0.0.1:8188');args=p.parse_args()
    if not args.reference.is_file():p.error('参考图不存在。')
    if any(style not in {e['id'] for e in catalog()} for style in args.styles):p.error('未知风格。')
    if args.one:return one_case(args)
    args.out.mkdir(parents=True,exist_ok=True);records=[]
    for style in args.styles:
        # A fresh process per style releases CPU segmentation arenas and sees current code.
        command=[sys.executable,'-u','-m','tools.verify_lora_walks','--reference',str(args.reference.resolve()),
            '--out',str(args.out.resolve()),'--one',style,'--seed',str(args.seed),'--url',args.url]
        subprocess.run(command,check=True)
        records.append(json.loads((args.out/style/'acceptance.json').read_text('utf-8')))
        write_json(args.out/'comparison.json',{'records':records,'same_source_reference':str(args.reference.resolve()),
            'seed':args.seed,'action':'walk','canvas':[768,1024],'frames':8,'fps':8,'steps':20,'sequential':True})


if __name__=='__main__':main()
