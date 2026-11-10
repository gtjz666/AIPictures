"""Standalone instrumental music jobs, serial with all video/image inference."""
import json
import math
import os
from pathlib import Path
import subprocess
import time
import numpy as np
from .engine import Cancelled
from .storage import write_json


def settings(data):
    path=Path(data)/'audio-settings.json'
    try:
        config=json.loads(path.read_text('utf-8'))
        if not config.get('validated') or not Path(config['python']).is_file() or not Path(config['model_root']).is_dir():return {}
        return config
    except (OSError,ValueError,KeyError):return {}


def generate(folder,params,cancel,emit):
    from .motion_native_backend import release_shared
    from .owned_process import OwnedProcessJob
    from .video_audio import read_audio,save_wav
    folder=Path(folder);config=params['audio_settings'];started=time.monotonic()
    manifest=dict(kind='audio',status='running',params=params)
    write_json(folder/'audio.json',manifest)
    try:
        if cancel.is_set():raise Cancelled('音频任务已取消。')
        if type(params.get('seconds')) not in (int,float) or not math.isfinite(params['seconds']) or not 10<=params['seconds']<=180:raise ValueError('器乐配乐时长应为10–180秒。')
        if not isinstance(params.get('prompt'),str) or not params['prompt'].strip() or len(params['prompt'])>8000:raise ValueError('音频要求无效。')
        if type(params.get('seed')) is not int or not 0<=params['seed']<2**64:raise ValueError('音频种子无效。')
        release_shared(params,folder=folder,cancel=cancel)
        caption=params['prompt']
        if any('\u4e00'<=c<='\u9fff' for c in caption) and params.get('intent_settings'):
            from .local_intent import LocalSession
            schema=dict(type='object',properties=dict(caption=dict(type='string')),required=['caption'],additionalProperties=False)
            emit('audio_stage',dict(message='正在整理音频要求…'))
            with LocalSession(params['intent_settings'],folder/'prompt',cancel,emit) as session:
                raw,_=session.complete([dict(role='system',content='Translate the user request into a faithful English instrumental music caption. Preserve instruments, mood, tempo and exclusions. No lyrics or invented story. Return JSON.'),dict(role='user',content=caption)],schema=schema,max_tokens=900)
            caption=json.loads(raw)['caption'].strip()
            if not caption:raise ValueError('音频要求未完成整理。')
        request=dict(config,out=str((folder/'audio-master.wav').resolve()),caption=caption,seconds=params['seconds'],seed=params['seed'])
        write_json(folder/'request.json',request)
        command=[config['python'],'-u',str(Path(__file__).with_name('audio_worker.py').resolve()),str((folder/'request.json').resolve())]
        emit('audio_stage',dict(message='正在生成独立器乐配乐…'))
        owner=None
        with (folder/'audio.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,
                env=dict(os.environ,PYTHONIOENCODING='utf-8',HF_HUB_OFFLINE='1'),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                owner=OwnedProcessJob(process.pid);emit('audio_process',dict(pid=process.pid,owner=owner))
                if cancel.is_set():raise Cancelled('音频任务已取消。')
                process.stdin.write(b'go\n');process.stdin.flush();process.stdin.close()
                while process.poll() is None:
                    if cancel.wait(.2):raise Cancelled('音频任务已取消，未继续占用模型。')
            finally:
                if owner:owner.close()
                if process.poll() is None:process.terminate();process.wait(timeout=15)
                write_json(folder/'process.json',dict(pid=process.pid,status='stopped',returncode=process.returncode))
        lines=[line for line in (folder/'audio.log').read_text('utf-8',errors='replace').splitlines() if line.startswith('{')]
        detail=json.loads(lines[-1]) if lines else {}
        if process.returncode or not detail.get('ok'):raise ValueError('音频生成失败：'+str(detail.get('detail','请查看本次audio.log')))
        audio=read_audio(folder/'audio-master.wav',params['seconds'],cancel=cancel)
        rms=float(np.sqrt(np.mean(audio**2)))
        if rms<.0001:raise ValueError('生成音频接近静音，未作为完成结果。')
        save_wav(folder/'audio.wav',audio)
        manifest.update(status='completed',audio=str((folder/'audio.wav').resolve()),sample_rate=48000,
            duration_seconds=params['seconds'],rms=rms,elapsed_seconds=round(time.monotonic()-started,2),engine='ACE-Step 1.5 XL turbo',worker=detail,caption=caption)
        write_json(folder/'audio.json',manifest);return dict(manifest=str(folder/'audio.json'))
    except BaseException as exc:
        manifest.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));write_json(folder/'audio.json',manifest);raise
