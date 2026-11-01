"""Run one real, reproducible isolated H3 test; do not silently enable it in the UI."""
import argparse
import json
import shutil
import threading
from pathlib import Path

from aipictures.storage import write_json
from aipictures.video_generation import generate


def main():
    p=argparse.ArgumentParser(description='真实H3完整动画测试，完成后再注册到软件。不会覆盖已有任务。')
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',type=Path);p.add_argument('--prompt',default='')
    p.add_argument('--action',required=True);p.add_argument('--negative',default='')
    p.add_argument('--seconds',type=float,default=4);p.add_argument('--seed',type=int,default=20261101)
    p.add_argument('--width',type=int,default=768);p.add_argument('--height',type=int,default=1024)
    a=p.parse_args()
    machine=json.loads((a.root/'machine.json').read_text('utf-8'))
    if not machine.get('ready'):raise ValueError('请先完成独立安装。')
    if a.output.exists():raise ValueError('目标已有目录，请核对旧任务，或选择新目录。')
    if not a.reference and not a.prompt.strip():raise ValueError('没有参考图时请填写画面描述。')
    if a.reference and not a.reference.is_file():raise ValueError('参考图路径不存在。')
    if not 2<=a.seconds<=8:raise ValueError('首次受控验证使用2–8秒片段。')
    if not 0<=a.seed<2**64:raise ValueError('请使用0–2^64-1的固定种子。')
    if any(n<256 or n>2048 or n%32 for n in (a.width,a.height)):
        raise ValueError('画布应为256–2048像素，且为32的整数倍。')
    a.output.mkdir(parents=True)
    reference=None
    if a.reference:
        reference=a.output/('reference'+a.reference.suffix);shutil.copyfile(a.reference,reference)
    config={**machine,'validated':True,'encoder_root':machine['comfy_root'],'width':a.width,'height':a.height}
    params={'engine':'h3','h3_settings':config,'prompt':a.prompt,'negative':a.negative,
        'action_description':a.action,'reference':str(reference.resolve()) if reference else None,
        'seed':a.seed,'seconds':a.seconds,'url':'http://127.0.0.1:8188'}
    write_json(a.output/'params.json',params);cancel=threading.Event()
    def emit(kind,data):
        if kind in ('video_stage','progress'):print(kind,json.dumps(data,ensure_ascii=False),flush=True)
    try:print(generate(None,a.output,params,cancel,emit))
    except KeyboardInterrupt:cancel.set();raise


if __name__=='__main__':main()
