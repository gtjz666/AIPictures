"""Small serial audio decode from the application's private Ref2VA sampler."""
import json
import os
from pathlib import Path
import subprocess
from .owned_process import OwnedProcessJob
from .engine import Cancelled
from .storage import write_json


def decode(folder,latent,config,cancel,emit):
    out=folder/'animation.artifacts/audio.npy';request=folder/'audio-decode-request.json'
    write_json(request,dict(root=config['root'],source=config['source'],base=config['base'],device='cpu',latent=str(Path(latent).resolve()),out=str(out.resolve())))
    command=[config['python'],'-u',str(Path(__file__).with_name('reference_audio_worker.py').resolve()),str(request.resolve())]
    emit('video_stage',dict(message='画面采样进程已退出，正在用CPU解码原生音轨…'))
    with (folder/'audio-decode.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,
            env=dict(os.environ,PYTHONIOENCODING='utf-8'),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        owner=None
        try:
            owner=OwnedProcessJob(process.pid);emit('h3_process',dict(pid=process.pid,owner=owner))
            if cancel.is_set():raise Cancelled('音轨解码已取消。')
            process.stdin.write(b'go\n');process.stdin.flush();process.stdin.close()
            while process.poll() is None:
                if cancel.wait(.2):raise Cancelled('音轨解码已取消。')
        finally:
            if owner:owner.close()
            if process.poll() is None:process.terminate();process.wait(timeout=15)
    if process.returncode or not out.is_file():raise ValueError('原生音轨解码失败，画面和潜变量已保留，请查看audio-decode.log。')
    return out
