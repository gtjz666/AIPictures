"""Serial real-GPU comparisons. Reuse completed jobs; never silently resubmit."""
import argparse
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.storage import write_json
from aipictures.workflow import ImageRequest,build_workflow

CASES={
 'portrait':('photorealistic portrait of one adult woman, front view, looking at the camera, natural facial proportions, clear eyes, soft studio light, plain gray background',832,1216),
 'anime_body':('2D anime illustration of one adult female adventurer, full body front view, short purple hair, blue jacket and black trousers, standing naturally, two arms relaxed at her sides, two legs, brown boots, clean outlines, flat colors, plain light gray background',832,1216),
 'prop':('one small glass potion bottle filled with red liquid, cork stopper, isometric game item illustration, centered object, clear silhouette, hand painted shading, plain light gray background, no text',1024,1024),
 'scene':('hand painted 2D game background, a quiet forest village beside a river, wooden houses, stone bridge, soft morning sunlight, coherent perspective, detailed environment, no people',1216,832),
}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    client=ComfyClient('http://127.0.0.1:8188'); info=client.discover()
    baseline=next(n for n in info['checkpoints'] if 'sd_xl_base_1.0_0.9vae' in n)
    quality=next(n for n in info['checkpoints'] if 'Juggernaut-XL_v9_' in n)
    rows=[]
    for variant,model in [('baseline',baseline),('quality',quality)]:
        for case,(prompt,width,height) in CASES.items():
            folder=args.output/variant/case;folder.mkdir(parents=True,exist_ok=True)
            request=ImageRequest(model,prompt,'blurry, watermark, text, duplicate body parts',width,height,30,5.5,907012,'dpmpp_2m','karras')
            graph=build_workflow(request)
            completed=folder/'result.json'
            if completed.exists():
                result=json.loads(completed.read_text('utf-8')); seconds=None
            else:
                queue=client.request('/queue')
                if queue.get('queue_running') or queue.get('queue_pending'):
                    raise RuntimeError('Shared engine is busy. Resume later; no new comparison submitted.')
                write_json(folder/'workflow.json',graph);write_json(folder/'params.json',asdict(request))
                started=time.monotonic()
                def emit(kind,data):
                    if kind in ('queued','executing','progress'):print(variant,case,kind,json.dumps(data),flush=True)
                receipt=folder/'submission.json'
                if receipt.exists():
                    saved=json.loads(receipt.read_text('utf-8'))
                    if not saved.get('prompt_id'):raise RuntimeError('Submission outcome unknown; inspect saved record instead of retrying.')
                    result=client.resume(saved['prompt_id'],graph,folder,emit,threading.Event())
                else:result=client.generate(graph,folder,emit,threading.Event())
                seconds=round(time.monotonic()-started,2)
                result['seconds']=seconds;write_json(completed,result)
                release_idle_models(client)
            rows.append({'variant':variant,'case':case,'image':result['images'][0],
                         'seconds':result.get('seconds',seconds),'model':model})
            write_json(args.output/'comparison.json',{'status':'running','cases':rows,
                'fixed_seed':907012,'no_reference':True,'lora':'','quality_acceptance':'requires_visual_review'})
    write_json(args.output/'comparison.json',{'status':'completed','cases':rows,'fixed_seed':907012,
        'no_reference':True,'lora':'','same_sampling_parameters':True,'quality_acceptance':'requires_visual_review'})
    print('REAL_COMPARISONS_COMPLETE',flush=True)


if __name__=='__main__':main()
