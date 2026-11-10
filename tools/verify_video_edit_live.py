"""One real multi-reference source-video replacement; no automatic rerolls."""
import argparse
import json
import shutil
import threading
from pathlib import Path
from PIL import Image
from aipictures.storage import write_json
from aipictures.video_script import prompt,write_script
from aipictures.video_generation import generate
from aipictures.video_edit import organize,FORMAT
from aipictures.local_intent import settings as intent_settings
from aipictures.h3_backend import settings as h3_settings
from aipictures.motion_native_backend import settings as native_settings,release_shared
from aipictures.motion_guide import inspect
from aipictures.workflow_library import digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--character',type=Path,required=True);p.add_argument('--seconds',type=int,default=30)
    a=p.parse_args();root=a.output.resolve();root.mkdir(parents=True,exist_ok=False);cancel=threading.Event()
    def emit(kind,value):
        if kind in ('video_stage','intent_stage','chain_progress','progress'):
            with (root/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(kind=kind,data=value),ensure_ascii=False)+'\n')
        elif kind=='h3_process':write_json(root/'active-process.json',dict(pid=value['pid']))
    media=root/'inputs';media.mkdir();source=media/('source'+a.source.suffix);shutil.copyfile(a.source,source)
    character=media/'image_1.png';shutil.copyfile(a.character,character)
    style=media/'image_2.png'
    with Image.open(source) as im:im.seek(min(8,im.n_frames-1));im.convert('RGBA').save(style)
    brief=('将参考视频里的蓝发人物替换为图1的紫发绿眼角色，保留图1的白色无袖衬衫、黑色领结、黑色短裤、长袜和棕色鞋。'
           '仅取图2的Q版头身比、线条和柔和上色，不取图2的蓝发、女仆装、头饰、尾巴。背景、动作顺序、节奏、方向和镜头跟随源视频。'
           '本次明确循环参考动作直到成片结束。配轻快的器乐背景音乐，无人声，无字幕。')
    release_shared({},folder=root,cancel=cancel)
    script=organize(intent_settings(a.data),brief,a.seconds,'bright',{1:character,2:style},root/'intent',cancel,emit)
    params=dict(mode='video',backend='standalone',engine='h3',creation_kind='long_video_edit',audio_mode='h3_native',
        h3_settings=h3_settings(a.data),motion_native_settings=native_settings(a.data),seconds=a.seconds,seed=20261110,
        prompt=prompt(script),negative=script['negative_prompt'],short_script=script,prompt_layout='unified',defer_exports=True,
        reference=str(character),reference_role='appearance',reference_usage='',motion_reference=str(source),motion_source=inspect(source),
        motion_start=0.,motion_repeat=True,motion_allow_tail_hold=False,motion_max_side=512,motion_timeline=[],motion_timeline_clock='output',
        motion_prompt_format=FORMAT,video_edit_refs=[dict(number=n,model_input=n,path=str(path),sha256=digest(path)) for n,path in ((1,character),(2,style))],music_style='bright',music_file=None,url=None)
    write_script(root,script);write_json(root/'job.json',dict(status='running',params=params,explicit_reference_repeat=True))
    try:
        result=generate(None,root,params,cancel,emit)
        write_json(root/'job.json',dict(status='completed',params=params,result=result));print('REAL_VIDEO_EDIT_COMPLETE',flush=True)
    except BaseException as exc:
        cancel.set();write_json(root/'job.json',dict(status='failed',params=params,error=str(exc)));raise


if __name__=='__main__':main()
