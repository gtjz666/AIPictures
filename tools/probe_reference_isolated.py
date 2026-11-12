"""Own a private standard Comfy process for matched reference experiments."""
import argparse,os,socket,subprocess,sys,time
from pathlib import Path
from urllib.error import URLError
from aipictures.engine import ComfyClient,EngineUnavailable
from aipictures.owned_process import OwnedProcessJob,gated_module_command
from aipictures.storage import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--session',type=Path,required=True);p.add_argument('--cases',type=Path,nargs='+',required=True)
    p.add_argument('--comfy-source',type=Path,required=True)
    p.add_argument('--model-paths-config',type=Path,required=True)
    p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--disable-cuda-malloc',action='store_true');args=p.parse_args()
    root=args.session.resolve();root.mkdir(parents=True,exist_ok=False)
    for name in ('output','user'):(root/name).mkdir()
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    source=args.comfy_source.resolve();python=source/'.venv/Scripts/python.exe'
    if not python.is_file() or not (source/'main.py').is_file():raise ValueError('Expected an existing standard ComfyUI source and environment')
    command=[str(python),'-u','-m','main','--listen','127.0.0.1','--port',str(port),
        '--extra-model-paths-config',str(args.model_paths_config.resolve()),
        '--input-directory',str(args.input_root.resolve()),
        '--output-directory',str(root/'output'),'--user-directory',str(root/'user'),
        '--database-url','sqlite:///'+(root/'user/comfyui.db').as_posix(),
        '--disable-all-custom-nodes','--whitelist-custom-nodes','AIPicturesRuntime','--disable-api-nodes','--disable-auto-launch',
        '--disable-dynamic-vram','--disable-async-offload','--disable-pinned-memory','--disable-smart-memory','--reserve-vram','1.0']
    if args.disable_cuda_malloc:command.append('--disable-cuda-malloc')
    owner=None;child=None;client=ComfyClient(f'http://127.0.0.1:{port}');started=time.monotonic()
    write_json(root/'command.json',dict(command=command,cwd=str(source),shared_server_unchanged=True,fresh_baselines=True))
    with (root/'backend.log').open('w',encoding='utf-8') as log:
        try:
            child=subprocess.Popen(gated_module_command(command,startup_trace=root/'startup'),cwd=source,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,
                env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1'),creationflags=subprocess.CREATE_NO_WINDOW)
            owner=OwnedProcessJob(child.pid);child.stdin.write(b'go\n');child.stdin.flush();child.stdin.close()
            write_json(root/'process.json',dict(pid=child.pid,url=client.url,status='starting'))
            while True:
                if child.poll() is not None:raise ValueError('Private backend exited before ready')
                try:
                    info=client.request('/object_info',timeout=2)
                    if 'AIPicturesReleaseCompletedEncoders' not in info:raise ValueError('Private runtime node missing')
                    break
                except (EngineUnavailable,TimeoutError,URLError):pass
                if time.monotonic()-started>180:raise TimeoutError('Private backend not ready')
                time.sleep(.4)
            print('Private backend ready; starting fresh matched baselines',flush=True)
            write_json(root/'startup/startup-ready.json',dict(url=client.url))
            write_json(root/'process.json',dict(pid=child.pid,url=client.url,status='ready'))
            os.environ['AIPICTURES_PROBE_URL']=client.url;os.environ['AIPICTURES_PROBE_FRESH_BASELINES']='1'
            sys.argv=['probe_reference_ablation','--proof',str(root/'experiments'),'--input-root',str(args.input_root.resolve()),'--cases',*[str(p.resolve()) for p in args.cases],'--base']
            from tools.probe_reference_ablation import main as experiment
            experiment()
        finally:
            if owner:owner.close()
            if child:
                if child.poll() is None:child.wait(timeout=20)
                write_json(root/'process.json',dict(pid=child.pid,url=client.url,status='stopped',returncode=child.returncode))


if __name__=='__main__':main()
