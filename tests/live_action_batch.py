"""Bounded real model action checks; server serializes jobs, no CPU matting overlaps inference."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from aipictures.engine import ComfyClient
from aipictures.pose_animation import generate
from aipictures.storage import DATA,write_json


def main():
    root=DATA/'pose-action-tests'/datetime.now().strftime('%Y%m%d_%H%M%S'); root.mkdir(parents=True)
    source=DATA/'references/be93d02d63944509ba617f5c90021bd0.png'
    def run(action):
        folder=root/action; folder.mkdir(); started=time.monotonic()
        def emit(kind,data):
            if kind=='pose_video_event' and data['event'] in ('queued','progress'):
                print(json.dumps({'action':action,'event':data},ensure_ascii=True),flush=True)
        result=generate(ComfyClient(),folder,'参考图中的同一角色，保持一致','多余肢体，多余脚掌，重影，文字，水印',
            20261029,8,8,emit,threading.Event(),source,steps=6,action=action,fast=True,raw_only=True)
        record={'action':action,'functional_execution_passed':True,'visual_review':'pending',
            'folder':str(folder),'result':result,'elapsed_seconds':round(time.monotonic()-started,1),
            'parameters':'6 steps accelerated diagnostic; not the default 20-step configuration'}
        write_json(folder/'acceptance.json',record); return record
    with ThreadPoolExecutor(max_workers=4) as pool: records=list(pool.map(run,('idle','run','jump','reach')))
    write_json(root/'acceptance.json',{'records':records,'visual_review':'pending'})
    write_json(DATA/'pose-action-batch-latest.json',{'folder':str(root),'records':records})
    print('Real action batch complete:',root,flush=True)


if __name__=='__main__': main()
