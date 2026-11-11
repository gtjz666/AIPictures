"""Reproduce a frozen user job and compare reference conditioning, without retries."""
import argparse,json,threading,time
from pathlib import Path
from dataclasses import replace
from PIL import Image,ImageOps
from aipictures.engine import ComfyClient
from aipictures.workflow import ImageRequest
from aipictures.multi_reference import build
from aipictures.reference_input import opaque_reference
from aipictures.structure_control import ADAPTER
from aipictures.storage import write_json
from aipictures.workflow_library import digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True);p.add_argument('--subject',type=Path,required=True)
    p.add_argument('--proof',type=Path,required=True);p.add_argument('--modes',nargs='+',default=['rgb_full','rgb_subject','depth_subject'])
    args=p.parse_args();args.proof.mkdir(parents=True,exist_ok=False)
    params=json.loads((args.job/'job.json').read_text('utf-8'))['params'];binding=params['structure_binding']
    refs={r['number']:Path(r['source']) for r in params['references']}
    original_hashes={str(p):digest(p) for p in refs.values()}
    c=ComfyClient();q=c.request('/queue')
    if q['queue_running'] or q['queue_pending']:raise ValueError('Backend busy; no comparisons submitted')
    info=c.request('/object_info')
    def upload(path,name):
        with Image.open(path) as image:rgb=opaque_reference(ImageOps.exif_transpose(image).convert('RGBA'))
        target=args.proof/name;rgb.save(target);return c.upload_image(target)
    source=upload(refs[binding['structure']],'source.png');full=upload(refs[binding['identity']],'identity-full.png')
    subject=upload(args.subject,'identity-subject.png');depth=c.upload_image(Path(params['structure_evidence']['depth']))
    command='Repose the woman from Image 2 into the exact complete body pose shown in Image 1. Preserve the woman\'s face, hair, body build and clothes from Image 2. Image 1 determines the entire body layout, legs, arms and hands; Image 2 supplies her appearance. Produce one anatomically coherent person.'
    req=ImageRequest(params['checkpoint'],command,'',params['width'],params['height'],4,1.,params['seed'],'euler','flux2')
    results=[]
    for mode in args.modes:
        if mode not in ('rgb_full','rgb_subject','depth_subject'):raise ValueError(mode)
        folder=args.proof/mode;folder.mkdir()
        controlled=mode=='depth_subject'
        graph,mapping=build(replace(req,positive=('refcontrol. '+command if controlled else command)),info,{1:depth if controlled else source,2:full if mode=='rgb_full' else subject})
        if controlled:
            graph['structure_adapter']=dict(class_type='LoraLoaderModelOnly',inputs=dict(model=['model',0],lora_name=ADAPTER,strength_model=.9))
            graph['release' if 'release' in graph else 'guider']['inputs']['model']=['structure_adapter',0]
        write_json(folder/'workflow.json',graph);started=time.monotonic();print('Starting '+mode,flush=True)
        result=c.generate(graph,folder,lambda *_:None,threading.Event());write_json(folder/'result.json',result)
        results.append(dict(mode=mode,elapsed=time.monotonic()-started,result=result['images'],prompt_id=result['prompt_id']))
        print('Completed '+mode,flush=True)
    assert all(digest(Path(p))==sha for p,sha in original_hashes.items())
    write_json(args.proof/'comparison.json',dict(source_job=str(args.job),seed=req.seed,width=req.width,height=req.height,source_hashes=original_hashes,results=results,review_required=True))
    from aipictures.engine_service import release_idle_models
    release_idle_models(c)


if __name__=='__main__':main()
