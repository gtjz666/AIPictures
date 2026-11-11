"""Bounded, explicit Vibe bone-render -> current Ref2VA feasibility probe."""
import argparse
import json
import shutil
import threading
from pathlib import Path
from aipictures.frame_motion_input import folder_frames,import_frames
from aipictures.motion_native_backend import settings
from aipictures.storage import write_json
from aipictures.video_generation import generate
from aipictures.workflow_library import digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rendered',type=Path,required=True);parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True);parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--run',action='store_true');args=parser.parse_args()
    if not args.run:raise ValueError('This model probe needs explicit --run; normal UI remains unchanged')
    folder=args.folder.resolve();folder.mkdir(parents=True,exist_ok=False);cancel=threading.Event()
    frames,fps=folder_frames(args.rendered);source,meta=import_frames(frames,fps,folder/'motion_inputs',cancel)
    reference=folder/'character.png';shutil.copyfile(args.reference,reference)
    brief='将图1的人物替换参考动画中的灰色人偶，仅保留图1的人物外形与衣着，动作、先后顺序与时间完全跟随参考动画。'
    params=dict(engine='h3',seconds=1.,seed=20261111,prompt=brief,source_brief=brief,user_prompt=brief,negative='',prompt_layout='unified',
        reference=str(reference),reference_role='appearance',reference_usage='',creation_kind='sprite_reference_edit',defer_exports=True,
        motion_prompt_format='video_edit_multi_v1',motion_native_settings=settings(args.data),motion_reference=str(source),motion_start=0.,
        motion_repeat=False,motion_allow_tail_hold=False,motion_max_side=512,motion_source=meta,motion_timeline=[],motion_timeline_clock='output',
        video_edit_refs=[dict(number=1,path=str(reference),sha256=digest(reference),model_input=1)],url='http://127.0.0.1:8188')
    write_json(folder/'params.json',params);write_json(folder/'scope.json',dict(original_render=str(args.rendered.resolve()),
        seconds=1,pose_control_branch=False,joint_detection_added=False,normal_ui_enabled=False,source_code_controls_proxy_only=True))
    print(generate(None,folder,params,cancel,lambda kind,value:print(kind,flush=True)),flush=True)


if __name__=='__main__':main()
