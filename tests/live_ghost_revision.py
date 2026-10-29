"""Actual 20-step sprite test, with a monitor that can cancel only its own job."""
import json
import subprocess
import threading
import time
import ctypes
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
    # The duplicate is idle: drop its caches, without interrupting or stopping it.
    if url!='http://127.0.0.1:8188': release_idle_models(ComfyClient())
    release_idle_models(client)
    root=DATA/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+'ghost_revision');root.mkdir(parents=True)
    print('Folder:',root,flush=True)
    cancel=threading.Event(); done=threading.Event(); readings=[]; abort=[]; progress=[]
    def monitor():
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in
                ('total_physical','available_physical','total_pagefile','available_pagefile','total_virtual','available_virtual','extended')]
        while not done.wait(10):
            try:
                memory=Memory();memory.length=ctypes.sizeof(memory)
                ok=ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
                if ok and memory.available_pagefile<2*1024**3:
                    abort.append('Available system commit below 2 GiB; cancel this test only.')
                    write_json(root/'memory-stop.json',abort);cancel.set();return
                result=subprocess.run(['nvidia-smi','--query-gpu=temperature.gpu,utilization.gpu,memory.used',
                    '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                values=[float(value.strip()) for value in result.stdout.strip().split(',')]
                readings.append({'elapsed':round(time.monotonic()-started,1),'temperature':values[0],
                    'gpu_percent':values[1],'vram_mib':values[2]})
                write_json(root/'hardware-readings.json',readings)
                if values[0]>=90:
                    abort.append('GPU reached 90C; cancel this test only.');cancel.set();return
            except Exception as exc: readings.append({'monitor_error':str(exc)})
    def emit(kind,data):
        if kind=='pose_video_event' and data['event']=='progress':
            progress.append(data['data']);print('progress',data['data'],flush=True)
        elif kind in ('reference_stage','frame_ready'): print(kind,data,flush=True)
    started=time.monotonic(); watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
    try:
        result=generate(client,root,params['prompt'],params['negative'],params['seed'],8,params['fps'],emit,cancel,
            params['reference'],steps=20,action='walk')
        write_json(root/'acceptance.json',{'functional_execution_passed':True,'visual_review':'pending',
            'source':str(source),'differences':['8 export frames instead of 16','Wan v2 thin pose rendering',
            'measured fingers only','crisp instantaneous-pose instructions','retain generated matte transparency'],
            'url':url,'steps':20,'fast_lora':False,'progress_count':len(progress),
            'elapsed_seconds':round(time.monotonic()-started,2),'result':result})
        print('Complete:',root,flush=True)
    finally:
        done.set();watcher.join(timeout=6);write_json(root/'hardware-readings.json',readings)
        if abort: write_json(root/'resource-stop.json',abort)


if __name__=='__main__': main()
