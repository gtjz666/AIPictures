"""One explicit native Ref2VA acceptance run; existing submissions are never repeated."""
import argparse
import json
import threading
from pathlib import Path
from aipictures.storage import write_json
from aipictures.video_generation import generate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--motion',type=Path,required=True);p.add_argument('--image',type=Path,required=True)
    p.add_argument('--prompt-file',type=Path);p.add_argument('--negative-file',type=Path)
    p.add_argument('--seconds',type=float,default=2.3);p.add_argument('--seed',type=int,default=20261102)
    a=p.parse_args();a.folder.mkdir(parents=True,exist_ok=False)
    config=json.loads(a.config.read_text('utf-8'))
    params=dict(engine='h3',prompt_layout='unified',prompt='Keep the yellow creature from <Picture 1>, including its big green eyes, cream belly and dark hands and feet. '
        'The yellow creature performs the punch and retract movement shown by <Video 1>. Animate the creature only; do not introduce the human performer. '
        'Keep a fixed camera and the whole creature visible, with consistent colors and shape.',negative='duplicate subject, extra limbs, human face, white hair, outfit from the motion guide, ghost silhouettes',
        reference=str(a.image.resolve()),motion_reference=str(a.motion.resolve()),motion_repeat=True,motion_max_side=512,
        motion_native_settings=config,seconds=a.seconds,seed=a.seed,_native_probe=True)
    if a.prompt_file:params['prompt']=a.prompt_file.read_text('utf-8')
    if a.negative_file:params['negative']=a.negative_file.read_text('utf-8')
    from aipictures.frame_motion_input import copy_source
    for key,path in [('motion_reference',a.motion),('reference',a.image)]:
        target=a.folder/(key+path.suffix);copy_source(path,target,threading.Event());params[key]=str(target.resolve())
    write_json(a.folder/'job.json',dict(status='running',params=params))
    def event(kind,data):
        if kind in ('video_stage','progress','queued','execution_error'):
            print(json.dumps(dict(event=kind,data=data),ensure_ascii=False,default=str),flush=True)
    try:
        result=generate(None,a.folder,params,threading.Event(),event)
        write_json(a.folder/'job.json',dict(status='completed',params=params,result=result))
        print('NATIVE_MOTION_COMPLETE',flush=True)
    except Exception as exc:
        write_json(a.folder/'job.json',dict(status='failed',params=params,error=str(exc)));raise


if __name__=='__main__':main()
