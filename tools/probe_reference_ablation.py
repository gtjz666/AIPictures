"""Frozen graph ablations; reuse completed baselines and resume only known prompt IDs."""
import argparse,copy,json,os,threading,time
from pathlib import Path
from aipictures.engine import ComfyClient
from aipictures.storage import write_json
from aipictures.workflow_library import digest

SHORT='refcontrol. Transfer the complete pose and composition from Image 1 to the subject in Image 2. Preserve Image 2 identity, proportions, clothing, colors and rendering.'
CONDITIONS=('auto','no_caption','short','trigger_only','empty')


def change_text(graph,params,condition):
    reference=copy.deepcopy(graph);graph=copy.deepcopy(graph);caption=params['positive'];original=graph['text']['inputs']['text']
    if not caption or not original.endswith(caption):raise ValueError('Frozen caption is not the graph suffix')
    text={'auto':original,'no_caption':original[:-len(caption)].rstrip(),'short':SHORT,'trigger_only':'refcontrol','empty':''}[condition]
    graph['text']['inputs']['text']=text
    # The prompt comparison is strictly one-node: identical inputs/model/sampler/canvas.
    audit=copy.deepcopy(graph);audit['text']['inputs']['text']=original
    if audit!=reference:raise ValueError('Prompt ablation changed a non-text input')
    return graph


def main():
    p=argparse.ArgumentParser();p.add_argument('--proof',type=Path,required=True);p.add_argument('--cases',type=Path,nargs='+',required=True)
    p.add_argument('--base',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--input-root',type=Path);args=p.parse_args()
    root=args.proof.resolve()
    if not args.resume:root.mkdir(parents=True,exist_ok=False)
    elif not (root/'plan.json').is_file():raise ValueError('No existing experiment plan')
    client=ComfyClient(os.environ.get('AIPICTURES_PROBE_URL','http://127.0.0.1:8188'));cancel=threading.Event();records=[];plan=[]
    fresh=os.environ.get('AIPICTURES_PROBE_FRESH_BASELINES')=='1'
    shared=args.input_root or Path(os.environ['LOCALAPPDATA'])/'Comfy-Desktop/ComfyUI-Shared/input'
    for case_no,job in enumerate(args.cases):
        job=job.resolve();params=json.loads((job/'job.json').read_text('utf-8'))['params'];graph=json.loads((job/'workflow.json').read_text('utf-8'))
        for key in ('image_1','image_2'):
            image=shared/graph[key]['inputs']['image']
            if not image.is_file():raise ValueError('Original Comfy input missing: '+str(image))
        case=dict(name=f'case_{case_no+1}',job=str(job),params=params,graph=graph,
            graph_sha256=digest(job/'workflow.json'),images={k:dict(path=str(shared/graph[k]['inputs']['image']),sha256=digest(shared/graph[k]['inputs']['image'])) for k in ('image_1','image_2')})
        records.append(case)
        for offset in range(3):
            for mode in ('auto','no_caption','short'):
                plan.append(dict(case=case['name'],seed=params['seed']+offset,offset=offset,condition=mode,base=False))
        for mode in ('trigger_only','empty'):plan.append(dict(case=case['name'],seed=params['seed'],offset=0,condition=mode,base=False))
        if args.base:plan.append(dict(case=case['name'],seed=params['seed'],offset=0,condition='short',base=True))
    frozen=dict(cases=records,trials=plan,protocol=dict(seeds='Original, original+1, original+2, chosen before viewing',fresh_baselines=fresh,
        main_conditions=['auto','no_caption','short'],exploratory=['trigger_only','empty'],
        base_configuration='Official FP8 Base + author workflow 20 steps/CFG5 + empty-text negative',
        timing_note='Wall time includes variable model/condition cache state; not an isolated language-model speed test',visual_review='Manual inspection, no calibrated accuracy percentage'))
    if args.resume:
        if json.loads((root/'plan.json').read_text('utf-8'))!=frozen:raise ValueError('Frozen experiment changed')
    else:write_json(root/'plan.json',frozen)
    cases={c['name']:c for c in records};summaries=[]
    # Keep all distilled trials together, then the larger Base configuration.
    plan=sorted(plan,key=lambda t:t['base'])
    for trial in plan:
        case=cases[trial['case']];tag=('base_' if trial['base'] else '')+trial['condition']+f'_s{trial["offset"]}'
        folder=root/trial['case']/tag;params=case['params']
        if (folder/'trial.json').is_file():
            saved=json.loads((folder/'trial.json').read_text('utf-8'))
            if saved['status']=='completed':summaries.append(saved);continue
            raise ValueError('Failed trial requires inspection, not automatic retry: '+str(folder))
        if trial['condition']=='auto' and trial['offset']==0 and not trial['base'] and not fresh:
            result=json.loads((Path(case['job'])/'result.json').read_text('utf-8'))
            if any(not Path(p).is_file() for p in result['images']):raise ValueError('Baseline output missing')
            entry=dict(trial,status='completed',reused_baseline=True,result=result['images'],prompt_id=result['prompt_id'],source_job=case['job'])
            write_json(folder/'trial.json',entry);summaries.append(entry);continue
        graph=change_text(case['graph'],params,trial['condition']);graph['noise']['inputs']['noise_seed']=trial['seed']
        if trial['base']:
            info=client.request('/object_info');name='flux-2-klein-base-4b-fp8.safetensors'
            if name not in info['UNETLoader']['input']['required']['unet_name'][0]:
                print('Base not yet available; distilled results preserved. Resume after verified download.',flush=True)
                write_json(root/'progress.json',dict(completed=summaries,deferred=trial));return
            graph['model']['inputs']['unet_name']=name;graph['sigmas']['inputs']['steps']=20;graph['guider']['inputs']['cfg']=5.
            graph['negative']=dict(class_type='CLIPTextEncode',inputs=dict(clip=['clip',0],text=''))
            if 'release' in graph:
                graph['encoded_dependencies']=dict(class_type='ConditioningCombine',inputs=dict(conditioning_1=graph['guider']['inputs']['positive'],conditioning_2=graph['guider']['inputs']['negative']))
                graph['release']['inputs']['conditioning']=['encoded_dependencies',0]
        existing=folder/'submission.json'
        if existing.is_file():
            submission=json.loads(existing.read_text('utf-8'));prompt_id=submission.get('prompt_id')
            if not prompt_id:raise ValueError('Unknown submission state; no duplicate POST')
            if json.loads((folder/'workflow.json').read_text('utf-8'))!=graph:raise ValueError('Existing workflow differs')
            result=client.resume(prompt_id,graph,folder,lambda *_:None,cancel);elapsed=None
        else:
            q=client.request('/queue')
            if q['queue_running'] or q['queue_pending']:
                print('Other backend work detected; paused before next submission.',flush=True)
                write_json(root/'progress.json',dict(completed=summaries,deferred=trial));return
            for v in case['images'].values():
                if digest(Path(v['path']))!=v['sha256']:raise ValueError('Frozen input changed')
            if folder.exists():raise ValueError('Unfinished directory without submission; inspect first')
            write_json(folder/'workflow.json',graph);started=time.monotonic();print('Starting '+trial['case']+'/'+tag,flush=True)
            try:result=client.generate(graph,folder,lambda *_:None,cancel)
            except Exception as exc:
                write_json(folder/'trial.json',dict(trial,status='failed',error=str(exc)));raise
            elapsed=time.monotonic()-started
        write_json(folder/'result.json',result)
        entry=dict(trial,status='completed',reused_baseline=False,result=result['images'],prompt_id=result['prompt_id'],elapsed_seconds=elapsed)
        write_json(folder/'trial.json',entry);summaries.append(entry)
        write_json(root/'progress.json',dict(completed=summaries));print('Completed '+trial['case']+'/'+tag,flush=True)
    write_json(root/'results.json',dict(trials=summaries,requires_visual_review=True))
    from aipictures.engine_service import release_idle_models
    release_idle_models(client)


if __name__=='__main__':main()
