"""CPU-only native AV join with the installed engine's audio seam repair."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


def join(folder,params,results,cancel,emit):
    from .engine import Cancelled
    from .storage import write_json
    request=folder/'join-request.json';target=folder/'joined-native.mp4';config=params['h3_settings']
    report=folder/'join-result.json'
    if report.is_file():
        value=json.loads(report.read_text('utf-8'))
        target=folder/value.get('target_name','joined-native.mp4')
        from .workflow_library import digest
        valid_hash=target.is_file() and (not value.get('sha256') or value['sha256']==digest(target))
        if target.is_file() and valid_hash and value.get('exact_end') and value.get('frames')==round(params['seconds']*24) and value.get('seams_repaired')==len(results)-1:return target.resolve()
        raise ValueError('已有音画合并结果不完整，请检查，未覆盖。')
    if target.exists():
        if not params.get('resume_chain'):raise ValueError('已有未完成的音画合并文件，请显式继续，原文件保留。')
        target=folder/f'joined-native-{uuid4().hex[:8]}.mp4'
    write_json(request,dict(source=config['source'],sources=[r['video'] for r in results],target=str(target.resolve()),frames=round(params['seconds']*24)))
    env=dict(os.environ,FREEVIDEO_HOME=config['root'],PYTHONIOENCODING='utf-8')
    command=[config['python'],'-u',str(Path(__file__).resolve()),str(request.resolve())]
    emit('video_stage',dict(message='片段已生成，正在对齐原生音画与声音接缝…'))
    with (folder/'join.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            while process.poll() is None:
                if cancel.wait(.2):raise Cancelled('音画合并已取消。')
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=15)
    if process.returncode or not target.is_file():raise ValueError('原生声音合并失败，请查看join.log；片段均保留。')
    from .workflow_library import digest
    value=json.loads(report.read_text('utf-8'));value.update(target_name=target.name,sha256=digest(target));write_json(report,value)
    return target.resolve()


if __name__=='__main__':
    # Running as a script: no GUI/torch import, only the engine's CPU media helpers.
    value=json.loads(Path(sys.argv[1]).read_text('utf-8'));sys.path.insert(0,value['source'])
    from freevideo_engine.chain_join import join_files
    result=join_files([Path(p) for p in value['sources']],Path(value['target']),frames=value['frames'],expected=len(value['sources'])-1)
    if result['seams_repaired']!=len(value['sources'])-1:raise ValueError('Not all native audio seams were repaired')
    Path(sys.argv[1]).with_name('join-result.json').write_text(json.dumps(result,default=str,ensure_ascii=False),encoding='utf-8')
