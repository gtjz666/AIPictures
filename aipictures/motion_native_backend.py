"""Dedicated Ref2VA in a private, cancellable Comfy process; no shared-server changes."""
import json
import math
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from .engine import Cancelled, ComfyClient, EngineUnavailable
from .owned_process import OwnedProcessJob, gated_module_command
from .storage import write_json


def output_frames(seconds:float)->int:
    if not math.isfinite(seconds) or not 2<=seconds<=8:raise ValueError('参考动画输出时长应为2–8秒。')
    requested=math.ceil(seconds*24)
    return max(22,requested+(5-requested)%17)


def settings(data: Path) -> dict:
    try:
        config=json.loads((Path(data)/'motion-native-settings.json').read_text('utf-8'))
        if not config.get('validated'):return {}
        if not all(Path(config[k]).exists() for k in ('python','source','model_paths')):return {}
        if not (Path(config['source'])/'custom_nodes/aipictures_motion/__init__.py').is_file():return {}
        from .motion_native_graph import MODEL,VAE
        if not {MODEL,VAE}.issubset({Path(row['path']).name for row in config['models']}):return {}
        if not all(Path(row['path']).stat().st_size==row['bytes'] for row in config['models']):return {}
        return config
    except (OSError,ValueError,KeyError,TypeError):return {}


class NativeSession:
    """Private job ownership makes cancellation independent of a busy CUDA node."""
    def __init__(self,config:dict,folder:Path,cancel:threading.Event,emit):
        self.config=config;self.folder=Path(folder);self.cancel=cancel;self.emit=emit
        self.process=None;self.owner=None;self.output=None;self.stop=threading.Event()
        self.input=self.folder/'native_input';self.output_dir=self.folder/'native_output'

    def __enter__(self):
        if self.cancel.is_set():raise Cancelled('动作参考生成已取消。')
        self.input.mkdir(exist_ok=False);self.output_dir.mkdir(exist_ok=False)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.client=ComfyClient(f'http://127.0.0.1:{port}')
        command=[self.config['python'],'-u','-m','main','--listen','127.0.0.1','--port',str(port),
                 '--extra-model-paths-config',self.config['model_paths'],'--input-directory',str(self.input.resolve()),
                 '--output-directory',str(self.output_dir.resolve()),'--disable-all-custom-nodes',
                 '--whitelist-custom-nodes','aipictures_motion','--offline','--disable-dynamic-vram',
                 '--cache-none','--disable-smart-memory','--reserve-vram','1.0']
        write_json(self.folder/'native-command.json',dict(command=command,cwd=self.config['source']))
        self.output=(self.folder/'native.log').open('w',encoding='utf-8')
        try:
            self.process=subprocess.Popen(gated_module_command(command),cwd=self.config['source'],
                env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1'),stdin=subprocess.PIPE,
                stdout=self.output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.owner=OwnedProcessJob(self.process.pid)
            self.emit('h3_process',dict(pid=self.process.pid,owner=self.owner))
            self.process.stdin.write(b'go\n');self.process.stdin.flush();self.process.stdin.close()
            self.watcher=threading.Thread(target=self.watch_cancel,daemon=True);self.watcher.start()
            deadline=time.monotonic()+300
            while True:
                self.check()
                try:
                    self.info=self.client.request('/object_info',timeout=2)
                    break
                except (EngineUnavailable,TimeoutError):pass
                except OSError as exc:
                    if not isinstance(getattr(exc,'reason',None),TimeoutError):raise
                if time.monotonic()>deadline:raise ValueError('专用动作参考后端启动超过5分钟，请检查 native.log。未提交生成。')
                self.cancel.wait(.5)
            write_json(self.folder/'native-process.json',dict(pid=self.process.pid,url=self.client.url,status='running'))
            return self
        except BaseException:
            self.__exit__(None,None,None);raise

    def watch_cancel(self):
        while not self.stop.wait(.2):
            if self.cancel.is_set():
                if self.owner:self.owner.close()
                if os.name!='nt' and self.process and self.process.poll() is None:self.process.terminate()
                return

    def check(self):
        if self.cancel.is_set():raise Cancelled('动作参考任务已取消；原文件与已保存结果保留。')
        if self.process.poll() is not None:raise ValueError('专用动作参考后端已退出，请检查 native.log。')

    def __exit__(self,*_):
        self.stop.set()
        if self.owner:self.owner.close()
        if self.process:
            if self.process.poll() is None:
                if os.name!='nt' or self.owner is None:self.process.terminate()
                self.process.wait(timeout=15)
            write_json(self.folder/'native-process.json',dict(pid=self.process.pid,status='stopped',returncode=self.process.returncode))
        if self.output:self.output.close()


def release_shared(params:dict):
    from .engine_service import release_idle_models
    urls={params.get('url'),'http://127.0.0.1:8188','http://127.0.0.1:8189'}-{None}
    for url in urls:
        client=ComfyClient(url)
        try:
            queue=client.request('/queue',timeout=3)
            if queue.get('queue_running') or queue.get('queue_pending'):
                raise ValueError('其他本地生成任务正在运行，请完成后再制作参考动画。')
            release_idle_models(client)
        except EngineUnavailable:pass


def generate(folder:Path,params:dict,cancel:threading.Event,emit)->dict:
    from .motion_guide import prepare,prompt
    from .motion_native_graph import build
    from .video_io import encode_pngs
    from .workflow_library import digest
    from PIL import Image,ImageOps
    folder=Path(folder);config=params.get('motion_native_settings',{})
    length=output_frames(params['seconds'])
    if not config.get('validated') and not params.get('_native_probe'):
        raise ValueError('动作参考专用模型尚未通过本机验证；普通提示词动画不受影响。')
    if (folder/'native-command.json').exists():raise ValueError('此任务已有运行记录，请检查原任务，不重复提交。')
    release_shared(params)
    emit('video_stage',{'message':'正在准备动作序列并启动专用参考引擎…'})
    with NativeSession(config,folder,cancel,emit) as server:
        motion=prepare(Path(params['motion_reference']),server.input/'motion',math.ceil(params['seconds']*24)/24,
            params.get('motion_start',0.),cancel,emit,max_side=params.get('motion_max_side',512),
            align_h3=True,repeat=params.get('motion_repeat',False),encode_video=False,save_frames=True)
        expected=params.get('motion_source',{}).get('sha256')
        if expected and expected!=motion['source']['sha256']:raise ValueError('动作参考与入队记录不一致。')
        image=''
        if params.get('reference'):
            with Image.open(params['reference']) as original:
                if original.width*original.height>16_000_000:raise ValueError('角色参考图超过1600万像素，请先缩小。')
                rgba=ImageOps.exif_transpose(original).convert('RGBA')
                rgb=Image.new('RGB',rgba.size,(232,232,232));rgb.paste(rgba,mask=rgba.getchannel('A'))
                rgb.save(server.input/'character.png');image='character.png'
        text=prompt(params['prompt'],bool(image))
        if params.get('negative','').strip():text+='\nAvoid: '+params['negative'].strip()
        (folder/'prompt.txt').write_text(text,'utf-8')
        graph=build(server.info,text,params['seed'],config.get('width',768),config.get('height',1024),
                    length,'motion/frames.json',image)
        # This graph belongs to the private H3 server, not the shared image editor.
        write_json(folder/'workflow.json',graph)
        def event(kind,data):
            server.check()
            if kind=='executing':
                node=graph.get(str(data.get('node')),{}).get('class_type','')
                stage={'MiniMaxH3ReferenceToVideo':'正在理解角色与动作参考并编码…',
                       'UNETLoader':'正在加载专用动作参考模型…','VAEDecode':'正在解码完整动画…'}.get(node)
                if stage:emit('video_stage',dict(message=stage))
            emit(kind,data)
        try:result=server.client.generate(graph,folder/'native_result',event,cancel)
        except EngineUnavailable:
            if cancel.is_set():raise Cancelled('动作参考任务已取消；专用后端已停止。')
            raise
        paths=[Path(p) for p in result['images']]
        if len(paths)!=length:raise ValueError('生成帧数不完整，已保存结果保留，请检查 native_result。')
    target=folder/'animation_master.mp4';encode_pngs(paths,target,24,cancel)
    return dict(video=str(target.resolve()),native_frames=[str(p.resolve()) for p in paths],
                backend='ComfyUI/H3-Ref2VA',style_lora=False,motion=motion,
                frame_sha256=[digest(p) for p in paths])
