"""Verify old ImageBatch vs lossless TIFF through the actual backend, without any model nodes."""
import argparse
import json
from pathlib import Path
import threading
from PIL import Image
from aipictures.backend_connection import shared_backend_url
from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.pose_sequence import pack_poses
from aipictures.storage import write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sequence',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():raise ValueError('验证输出目录已存在，不能覆盖之前的记录。')
    original=json.loads((args.sequence/'video/workflow.json').read_text('utf-8'))
    paths=sorted((args.sequence/'poses').glob('pose_*.png'))
    if not paths:raise ValueError('未找到原始独立姿态 PNG。')
    args.out.mkdir(parents=True);report=pack_poses(paths,args.out/'poses.tiff')
    client=ComfyClient(shared_backend_url('http://127.0.0.1:8188'));cancel=threading.Event()
    while True:
        queue=client.request('/queue')
        if not queue.get('queue_running') and not queue.get('queue_pending'):break
        cancel.wait(5)
    release_idle_models(client)
    packed=client.upload_image(args.out/'poses.tiff',subfolder='AIPictures/pose_sequences')
    graph={key:node for key,node in original.items() if key.startswith('pose_')}
    graph['old_save']={'class_type':'SaveImage','inputs':{'images':original['8']['inputs']['pose_video'],'filename_prefix':'AIPictures/pose_batch_old'}}
    graph['packed']={'class_type':'LoadImage','inputs':{'image':packed}}
    graph['new_save']={'class_type':'SaveImage','inputs':{'images':['packed',0],'filename_prefix':'AIPictures/pose_batch_packed'}}
    write_json(args.out/'workflow.json',graph)
    result=client.generate(graph,args.out,lambda *_:None,cancel,
        submitted=lambda pid:write_json(args.out/'submitted.json',{'prompt_id':pid}))
    write_json(args.out/'result.json',result)
    outputs=result['history']['outputs'];items=[]
    for output in outputs.values():items.extend(item for item in output.get('images',[]) if item.get('type','output')=='output')
    mapping={item['filename']:Path(path) for item,path in zip(items,result['images'])}
    a=outputs['old_save']['images'];b=outputs['new_save']['images']
    assert len(a)==len(b)==len(paths)
    exact=[]
    for old,new in zip(a,b):
        with Image.open(mapping[old['filename']]) as before,Image.open(mapping[new['filename']]) as after:
            exact.append(before.convert('RGB').tobytes()==after.convert('RGB').tobytes())
    assert all(exact)
    report.update(passed=True,backend_pixel_exact=exact,url=client.url,prompt_id=result['prompt_id'],
        model_nodes_executed=False,old_pose_node_count=len(graph)-3,new_pose_node_count=1)
    write_json(args.out/'acceptance.json',report);release_idle_models(client)
    print(json.dumps({'passed':True,'frames':len(paths),'backend_pixel_exact':all(exact),'model_nodes_executed':False}))


if __name__=='__main__':main()
