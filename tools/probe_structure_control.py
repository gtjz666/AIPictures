"""Matched ordinary-reference / trained depth-control comparison; no auto retry."""
import argparse,json,threading,time
from pathlib import Path
from aipictures.engine import ComfyClient
from aipictures.workflow import ImageRequest
from aipictures.flux_klein import UNET
from aipictures.multi_reference import build
from aipictures.storage import write_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--proof',type=Path,required=True);p.add_argument('--depth',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--identity',type=Path,required=True)
    p.add_argument('--prompt');p.add_argument('--modes',nargs='+',choices=['ordinary','depth_untrained','depth_trained'],default=['ordinary','depth_untrained','depth_trained']);args=p.parse_args()
    args.proof.mkdir(parents=True,exist_ok=False);c=ComfyClient('http://127.0.0.1:8188');queue=c.request('/queue')
    if queue['queue_running'] or queue['queue_pending']:raise ValueError('Backend busy; comparison not submitted')
    info=c.request('/object_info');lora='flux2_klein_4b_refcontrol_depth.safetensors'
    assert lora in info['LoraLoaderModelOnly']['input']['required']['lora_name'][0]
    from PIL import Image,ImageOps
    from aipictures.reference_input import opaque_reference
    def upload(path,name):
        with Image.open(path) as im:rgb=opaque_reference(ImageOps.exif_transpose(im).convert('RGBA'))
        target=args.proof/name;rgb.save(target);return c.upload_image(target)
    identity=upload(args.identity,'identity.png');source=upload(args.source,'source.png');depth=c.upload_image(args.depth)
    prompt=args.prompt or 'The purple-haired anime woman wearing a white sleeveless blouse with black ribbon, dark shorts and dark thigh-high socks adopts the exact body pose and composition from Image 1. Preserve her character identity and clothes from Image 2. Keep the deeply bent outward knees, inward-folded lower legs, backward leaning torso and low pelvis.'
    results=[]
    for mode in args.modes:
        folder=args.proof/mode;folder.mkdir();req=ImageRequest(UNET,('refcontrol. '+prompt if mode!='ordinary' else prompt),'',512,512,4,1.,20261111,'euler','flux2')
        graph,mapping=build(req,info,{1:source if mode=='ordinary' else depth,2:identity})
        if mode=='depth_trained':
            graph['structure_adapter']=dict(class_type='LoraLoaderModelOnly',inputs=dict(model=['model',0],lora_name=lora,strength_model=.9))
            graph['release' if 'release' in graph else 'guider']['inputs']['model']=['structure_adapter',0]
        write_json(folder/'workflow.json',graph);started=time.monotonic();print('Starting '+mode,flush=True)
        result=c.generate(graph,folder,lambda *_:None,threading.Event());write_json(folder/'result.json',result)
        results.append(dict(mode=mode,elapsed=time.monotonic()-started,images=result['images'],prompt_id=result['prompt_id']))
        print('Completed '+mode,flush=True)
    write_json(args.proof/'comparison.json',dict(results=results,same_seed=True,same_dimensions=True,steps=4,review_required=True))
    from aipictures.engine_service import release_idle_models
    release_idle_models(c)

if __name__=='__main__':main()
