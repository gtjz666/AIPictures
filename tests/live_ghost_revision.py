"""Actual 20-step sprite test. No memory or temperature monitoring."""
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from aipictures.backend_connection import shared_backend_url
from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.pose_animation import generate
from aipictures.storage import DATA,write_json


def main():
    source=Path(r'C:\Users\qcy_2\Desktop\AIPictures\data\animations\20261029_111043_2e472f58')
    params=json.loads((source/'job.json').read_text('utf-8'))['params']
    url=shared_backend_url('http://127.0.0.1:8188'); client=ComfyClient(url)
    queue=client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'): raise RuntimeError('Existing jobs: defer the test.')
    release_idle_models(client)
    root=DATA/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+'ghost_revision');root.mkdir(parents=True)
    print('Folder:',root,flush=True)
    cancel=threading.Event();progress=[]
    def emit(kind,data):
        if kind=='pose_video_event' and data['event']=='progress':
            progress.append(data['data']);print('progress',data['data'],flush=True)
        elif kind in ('reference_stage','frame_ready'): print(kind,data,flush=True)
    started=time.monotonic()
    result=generate(client,root,params['prompt'],params['negative'],params['seed'],8,params['fps'],emit,cancel,
            params['reference'],steps=20,action='walk')
    write_json(root/'acceptance.json',{'functional_execution_passed':True,'visual_review':'pending','resource_monitoring':False,
            'source':str(source),'differences':['8 export frames instead of 16','Wan v2 thin pose rendering',
            'measured fingers only','crisp instantaneous-pose instructions','retain generated matte transparency'],
            'url':url,'steps':20,'fast_lora':False,'progress_count':len(progress),
            'elapsed_seconds':round(time.monotonic()-started,2),'result':result})
    print('Complete:',root,flush=True)


if __name__=='__main__': main()
