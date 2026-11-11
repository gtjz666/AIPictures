"""Serial text-to-SFX jobs; retain the natural decay instead of enforcing music energy."""
import json
import math
import os
from pathlib import Path
import subprocess
import time
from .engine import Cancelled
from .owned_process import OwnedProcessJob
from .storage import write_json


def generate(folder,params,cancel,emit):
    from .motion_native_backend import release_shared
    from .audio_prompt import fingerprint
    folder=Path(folder);config=params['audio_settings'];seconds=params['seconds'];start=time.monotonic()
    if (folder/'audio.json').exists() or (folder/'audio.wav').exists():raise ValueError('该音效目录已有任务，不重复生成或覆盖。')
    manifest=dict(kind='audio',status='running',params=params);write_json(folder/'audio.json',manifest)
    try:
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not .5<=seconds<=5:raise ValueError('游戏音效时长应为0.5–5秒。')
        if not isinstance(params.get('prompt'),str) or not params['prompt'].strip():raise ValueError('请填写音效需求。')
        if type(params.get('seed')) is not int or not 0<=params['seed']<2**64:raise ValueError('音效种子无效。')
        if cancel.is_set():raise Cancelled('音效任务已取消。')
        caption=params.get('caption_english')
        if not isinstance(caption,str) or not caption.strip() or params.get('caption_fingerprint')!=fingerprint(params['prompt'],params.get('negative','')):
            if any('\u4e00'<=c<='\u9fff' for c in params['prompt']):raise ValueError('请先完成本次音效需求的文字整理。')
            caption=params['prompt']
        release_shared(params,folder=folder,cancel=cancel)
        request=dict(config,caption=caption,seconds=seconds,seed=params['seed'],out=str((folder/'audio.wav').resolve()))
        write_json(folder/'request.json',request)
        command=[config['python'],'-u',str(Path(__file__).with_name('woosh_worker.py').resolve()),str((folder/'request.json').resolve())]
        emit('audio_stage',dict(message='正在生成游戏音效…'));owner=None
        with (folder/'audio.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,
                env=dict(os.environ,PYTHONIOENCODING='utf-8',HF_HUB_OFFLINE='1',HF_HOME=config['hf_home']),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                owner=OwnedProcessJob(process.pid);emit('audio_process',dict(pid=process.pid,owner=owner))
                if cancel.is_set():raise Cancelled('音效任务已取消。')
                process.stdin.write(b'go\n');process.stdin.flush();process.stdin.close()
                while process.poll() is None:
                    if cancel.wait(.2):raise Cancelled('音效任务已取消。')
            finally:
                if owner:owner.close()
                if process.poll() is None:process.terminate();process.wait(timeout=15)
                write_json(folder/'process.json',dict(pid=process.pid,status='stopped',returncode=process.returncode))
        lines=[line for line in (folder/'audio.log').read_text('utf-8',errors='replace').splitlines() if line.startswith('{')]
        detail=json.loads(lines[-1]) if lines else {}
        if process.returncode or not detail.get('ok'):raise ValueError('音效生成失败：'+str(detail.get('detail','请查看本次audio.log')))
        manifest.update(status='completed',audio=request['out'],duration_seconds=seconds,sample_rate=48000,channels=1,
            engine='Sony Woosh-Flow',caption=caption,worker=detail,elapsed_seconds=round(time.monotonic()-start,3),rms=detail['rms'])
        write_json(folder/'audio.json',manifest);return dict(manifest=str(folder/'audio.json'))
    except BaseException as exc:
        manifest.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));write_json(folder/'audio.json',manifest);raise
