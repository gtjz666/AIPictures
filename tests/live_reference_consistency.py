"""Same character/action/seed/steps; add the actual reference-face branch and palette stage."""
import argparse
import json
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from aipictures.engine import ComfyClient
from aipictures.pose_animation import generate
from aipictures.storage import DATA,write_json


def main():
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('--url',default='http://127.0.0.1:8189')
    args=parser.parse_args();source=Path(args.source)
    params=json.loads((source/'job.json').read_text('utf-8'))['params']
    motion=json.loads((source/'motion.json').read_text('utf-8'))
    client=ComfyClient(args.url);queue=client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):raise RuntimeError('现有引擎仍有任务，暂不提交比较。')
    # Reuse analysis metadata; original user assets and cached outputs are never changed.
    analysis=json.loads((source/'reference_analysis.json').read_text('utf-8'))
    original=Path(analysis['rig']).parent
    if (original/'analysis.json').is_file():
        target=DATA/'reference-analysis'/original.name;target.mkdir(parents=True,exist_ok=True)
        shutil.copy2(original/'analysis.json',target/'analysis.json')
    root=DATA/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+'reference_consistency');root.mkdir(parents=True)
    print('Folder:',root,flush=True);progress=[];started=time.monotonic()
    def emit(kind,data):
        if kind=='pose_video_event' and data['event']=='progress':
            progress.append(data['data']);print('progress',data['data'],flush=True)
        elif kind in ('reference_stage','frame_ready'):print(kind,data,flush=True)
    result=generate(client,root,params['prompt'],params['negative'],params['seed'],params['count'],params['fps'],emit,
        threading.Event(),params['reference'],steps=params['steps'],action=params['action'],motion=motion,face_condition=True)
    write_json(root/'acceptance.json',{'source':str(source),'functional_execution_passed':True,'visual_review':'pending',
        'inference_changes':['measured reference-face crop repeated across all pose frames'],
        'same_body_poses':True,'same_seed':True,'same_steps':True,'same_sampler_cfg_and_resolution':True,
        'postprocess_changes':['foreground regional original-reference palette'],
        'resource_monitoring':False,'progress_events':len(progress),'elapsed_seconds':time.monotonic()-started,'result':result})
    print('Complete:',root,flush=True)


if __name__=='__main__':main()
