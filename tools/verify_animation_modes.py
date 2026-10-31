"""Sequential native-quality action acceptance using the same production path as walking."""
import argparse
import json
from pathlib import Path
import threading
import time

from PIL import Image, ImageDraw, ImageFont

from aipictures.animation_actions import ACTIONS,PRESET_ACTIONS, output_indices
from aipictures.backend_connection import shared_backend_url
from aipictures.engine import ComfyClient
from aipictures.pose_animation import generate, check_models
from aipictures.storage import write_json


def inspect_exports(folder: Path) -> dict:
    manifest=json.loads((folder/'sequence.json').read_text('utf-8'))
    frames=[folder/f['image'] for f in manifest['frames']]
    with Image.open(folder/'sprite_sheet.png') as sheet:
        columns=manifest['exports']['columns'];width,height=manifest['canvas']
        equal=[];alpha=[]
        for i,path in enumerate(frames):
            with Image.open(path) as source:
                frame=source.convert('RGBA')
                rect=((i%columns)*width,(i//columns)*height,(i%columns+1)*width,(i//columns+1)*height)
                equal.append(frame.size==(width,height) and frame.tobytes()==sheet.crop(rect).convert('RGBA').tobytes())
                alpha.append(frame.getchannel('A').getextrema())
    passed=(manifest['status']=='completed' and len(frames)==manifest['frame_count'] and all(equal)
            and all(low==0 and high==255 for low,high in alpha)
            and all(f['post_color_rgb_preserved'] for f in manifest['frames'])
            and manifest['pose_selection']['source_indices']==output_indices(manifest['action'],len(frames),manifest['source_frame_count']))
    return {'functional_execution_passed':passed,'action':manifest['action'],
        'frames':len(frames),'native_size':manifest['canvas'],'sheet_roundtrip_exact':equal,
        'alpha_ranges':alpha,'sampling_prompt_id':manifest['sampling_prompt_id'],
        'decode_prompt_id':manifest['decode_prompt_id'],'timings':manifest['timings'],
        'visual_review':'pending; functional checks do not establish anatomical/color accuracy'}


def overview(root: Path, actions: list[str]) -> None:
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
    sheet=Image.new('RGB',(8*144,232*len(actions)),(242,243,245))
    draw=ImageDraw.Draw(sheet)
    for row,action in enumerate(actions):
        manifest=json.loads((root/action/'sequence.json').read_text('utf-8'))
        draw.text((8,row*232+2),ACTIONS[action][0],font=font,fill=(30,30,30))
        for i,item in enumerate(manifest['frames'][:8]):
            with Image.open(root/action/item['image']) as source:
                preview=source.convert('RGBA');preview.thumbnail((140,192),Image.Resampling.NEAREST)
                sheet.paste(preview,(i*144+(144-preview.width)//2,row*232+31),preview)
    sheet.save(root/'overview.png')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--actions',nargs='+',choices=PRESET_ACTIONS,default=['walk','idle','run','jump','squat','attack'])
    parser.add_argument('--url',default='http://127.0.0.1:8188')
    parser.add_argument('--seed',type=int,default=20261030)
    args=parser.parse_args()
    if not args.reference.is_file():parser.error('参考图不存在。')
    args.out.mkdir(parents=True,exist_ok=True)
    client=ComfyClient(shared_backend_url(args.url))
    check_models(client.discover()['object_info'])
    cancel=threading.Event();records=[]
    for action in args.actions:
        folder=args.out/action
        if folder.exists():
            if not (folder/'acceptance.json').is_file():
                raise ValueError(f'{folder} 包含未完成试验。请按 submitted.json 检查原任务，不能自动重复提交。')
            records.append(json.loads((folder/'acceptance.json').read_text('utf-8')));continue
        while True:
            queue=client.request('/queue')
            if not queue.get('queue_running') and not queue.get('queue_pending'):break
            print(json.dumps({'action':action,'state':'waiting_for_shared_queue'}),flush=True)
            cancel.wait(10)
        folder.mkdir()
        def emit(kind,data):
            if kind=='reference_stage' or kind in ('pose_video_event','decode_event') and data['event'] in (
                'queued','progress','executing','monitor_waiting','cancel_pending'):
                print(json.dumps({'action':action,'kind':kind,'data':data},ensure_ascii=True),flush=True)
        started=time.monotonic()
        try:
            generate(client,folder,'参考图中的同一角色，保持外观一致','重影，多余肢体，颜色缺失，模糊',
                     args.seed,8,8,emit,cancel,args.reference,steps=20,action=action,
                     detail='native',sampler='euler',color_mode='original')
            record=inspect_exports(folder)
            record['elapsed_seconds']=round(time.monotonic()-started,2)
            write_json(folder/'acceptance.json',record);records.append(record)
            write_json(args.out/'acceptance.json',{'url':client.url,'records':records,'parameters':{
                'steps':20,'detail':'native','size':[768,1024],'sampler':'euler','color_mode':'original',
                'sequential':True,'fast_lora':False}})
            overview(args.out,[r['action'] for r in records])
            print(json.dumps(record,ensure_ascii=True),flush=True)
            if not record['functional_execution_passed']:raise RuntimeError('输出验收未通过，请查看 acceptance.json。')
        except Exception as exc:
            write_json(args.out/'failure.json',{'action':action,'error':str(exc),'url':client.url})
            raise


if __name__=='__main__':main()
