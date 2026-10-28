"""Same saved reference/poses/seed/steps; change CFG alone to Animate's official 1.0."""
import argparse
import json
import time
import threading
import shutil
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from aipictures.engine import ComfyClient
from aipictures.engine_service import start_local_engine,release_idle_models
from aipictures.pose_animation import export_frames
from aipictures.storage import DATA,write_json


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('source'); args=parser.parse_args()
    source=Path(args.source); graph=json.loads((source/'video/workflow.json').read_text('utf-8'))
    original_cfg=graph['11']['inputs']['cfg']; graph['11']['inputs']['cfg']=1.
    root=DATA/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]); video=root/'video'; video.mkdir(parents=True)
    start_local_engine('http://127.0.0.1:8188',lambda *message:print(message,flush=True))
    client=ComfyClient(); release_idle_models(client)
    for name in ('motion.json','reference_analysis.json'): shutil.copy2(source/name,root/name)
    shutil.copytree(source/'poses',root/'poses')
    manifest=json.loads((source/'sequence.json').read_text('utf-8'))
    manifest.update(status='running',frames=[],timings={},ab_source=str(source),ab_only_change={'cfg':[original_cfg,1.]})
    write_json(root/'sequence.json',manifest); write_json(video/'workflow.json',graph)
    started=time.monotonic(); print('Comparison:',root,flush=True)
    def emit(kind,data):
        if kind in ('progress','reference_stage','frame_ready'): print(kind,data,flush=True)
    result=client.generate(graph,video,emit,threading.Event(),timeout=7200,
        submitted=lambda pid:write_json(video/'submitted.json',{'prompt_id':pid}))
    manifest['timings']['inference_wait_and_download_seconds']=round(time.monotonic()-started,3)
    write_json(video/'result.json',result); release_idle_models(client)
    motion=json.loads((root/'motion.json').read_text('utf-8'))
    exported=export_frames(root,result,manifest,motion,emit,threading.Event())
    manifest['timings']['total_seconds']=round(time.monotonic()-started,3); write_json(root/'sequence.json',manifest)
    write_json(root/'acceptance.json',{'functional_execution_passed':True,'visual_review':'pending','only_model_change_cfg':True,
        'source':str(source),'timings':manifest['timings'],'result':exported})
    print('Comparison complete:',root,flush=True)


if __name__=='__main__': main()
