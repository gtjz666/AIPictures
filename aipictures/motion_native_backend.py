"""Dedicated Ref2VA in a private, cancellable Comfy process; no shared-server changes."""
import json
import math
import os
import socket
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .engine import Cancelled, ComfyClient, EngineUnavailable
from .owned_process import OwnedProcessJob, gated_module_command
from .storage import write_json


def output_frames(seconds:float)->int:
    if not math.isfinite(seconds) or not 2<=seconds<=15:raise ValueError('单段参考动画应为2–15秒；较长动画请使用分段生成。')
    requested=math.ceil(seconds*24)
    return max(22,requested+(5-requested)%17)


def settings(data: Path) -> dict:
    try:
        config=json.loads((Path(data)/'motion-native-settings.json').read_text('utf-8'))
        if not config.get('validated'):return {}
        if not all(Path(config[k]).exists() for k in ('python','source','model_paths')):return {}
        private_nodes=Path(config['source'])/'custom_nodes/aipictures_motion'
        if not all((private_nodes/name).is_file() for name in ('__init__.py','frames.py','conditioning.py','stream_weights.py')):return {}
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
        self.folder.mkdir(parents=True,exist_ok=True)
        self.input.mkdir(exist_ok=False);self.output_dir.mkdir(exist_ok=False)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.client=ComfyClient(f'http://127.0.0.1:{port}')
        command=[self.config['python'],'-u','-m','main','--listen','127.0.0.1','--port',str(port),
                 '--extra-model-paths-config',self.config['model_paths'],'--input-directory',str(self.input.resolve()),
                 '--output-directory',str(self.output_dir.resolve()),'--disable-all-custom-nodes',
                 '--whitelist-custom-nodes','aipictures_motion','--offline','--disable-dynamic-vram',
                 '--cache-none','--disable-smart-memory','--reserve-vram','3.0']
        if os.name=='nt':command+=['--disable-async-offload','--disable-pinned-memory']
        write_json(self.folder/'native-command.json',dict(command=command,cwd=self.config['source'],
            environment={'AIPICTURES_STREAM_WEIGHTS':'1'},weights_loader='stream'),durable=True)
        self.output=(self.folder/'native.log').open('w',encoding='utf-8')
        try:
            self.process=subprocess.Popen(gated_module_command(command,startup_trace=self.folder),cwd=self.config['source'],
                env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1',AIPICTURES_STREAM_WEIGHTS='1'),stdin=subprocess.PIPE,
                stdout=self.output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.owner=OwnedProcessJob(self.process.pid)
            write_json(self.folder/'native-process.json',dict(pid=self.process.pid,
                url=self.client.url,status='starting'),durable=True)
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
            write_json(self.folder/'startup-ready.json',dict(ready=True,pid=self.process.pid),durable=True)
            write_json(self.folder/'native-process.json',dict(pid=self.process.pid,url=self.client.url,status='running'),durable=True)
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
        code=self.process.poll()
        if code is not None:
            if os.name=='nt' and code & 0xffffffff == 0xc0000005:
                raise ValueError('专用动作参考后端发生访问冲突（0xC0000005），任务已停止；请查看本次 native.log 和启动记录。')
            raise ValueError(f'专用动作参考后端已退出（代码 {code}），请检查 native.log。')

    def __exit__(self,*_):
        self.stop.set()
        if self.owner:self.owner.close()
        if self.process:
            if self.process.poll() is None:
                if os.name!='nt' or self.owner is None:self.process.terminate()
                self.process.wait(timeout=15)
            write_json(self.folder/'native-process.json',dict(pid=self.process.pid,status='stopped',returncode=self.process.returncode),durable=True)
        if self.output:self.output.close()


def release_shared(params:dict, *, folder:Path|None=None, cancel:threading.Event|None=None)->list[dict]:
    """Check the actual Desktop port and fail closed on refused cache release.

    /free acknowledges a request; it is not proof that GPU memory is already
    empty. Record that distinction, and never interrupt another client's queue.
    """
    from .backend_connection import desktop_urls,local_processes
    from .engine_service import release_idle_models
    records=[]
    try:
        if cancel is not None and cancel.is_set():raise Cancelled('动作参考任务已取消，未启动动画后端。')
        candidates=[params.get('url'),*desktop_urls(local_processes()),
                    'http://127.0.0.1:8188','http://127.0.0.1:8189']
        urls=dict.fromkeys(url.rstrip('/') for url in candidates if url)
        for url in urls:
            if cancel is not None and cancel.is_set():raise Cancelled('动作参考任务已取消，未启动动画后端。')
            row={'url':url,'status':'checking'};records.append(row)
            client=ComfyClient(url)
            try:
                queue=client.request('/queue',timeout=3)
            except EngineUnavailable:
                row['status']='offline';continue
            except Exception as exc:
                row.update(status='check_failed',error=str(exc))
                raise ValueError(f'无法确认本地后端 {url} 是否空闲，未启动动画后端；请检查连接。') from exc
            if not isinstance(queue,dict):
                row['status']='invalid_queue'
                raise ValueError(f'本地后端 {url} 返回了无效队列，未启动动画后端。')
            if queue.get('queue_running') or queue.get('queue_pending'):
                row['status']='busy'
                raise ValueError('其他本地生成任务正在运行，请完成后再制作参考动画。')
            # This helper rechecks the queue, including jobs arriving after our check.
            result=release_idle_models(client)
            if not result.get('released'):
                row.update(status='release_failed',reason=result.get('reason','unknown'))
                raise ValueError(f'本地后端 {url} 未接受模型释放请求，未启动动画后端；请等待其他任务结束或检查连接。')
            row['status']='release_requested'
        return records
    finally:
        if folder is not None:
            write_json(Path(folder)/'shared-release.json',{'backends':records,
                'completion_verified':False},durable=True)


def generate(folder:Path,params:dict,cancel:threading.Event,emit)->dict:
    from .motion_guide import prepare,prompt
    from .motion_native_graph import encoding,sampling
    from .video_io import encode_pngs
    from .workflow_library import digest
    from PIL import Image,ImageOps
    from .motion_prompt import FORMAT,compile_prompt
    prompt_format=params.get('motion_prompt_format','reference_roles_v1')
    if prompt_format not in ('reference_roles_v1',FORMAT):raise ValueError('未知动作提示词格式，未提交生成。')
    folder=Path(folder);config=params.get('motion_native_settings',{})
    length=output_frames(params['seconds'])
    if not config.get('validated') and not params.get('_native_probe'):
        raise ValueError('动作参考专用模型尚未通过本机验证；普通提示词动画不受影响。')
    if any((folder/p).exists() for p in ('native-command.json','native_encode','native_sample')):
        raise ValueError('此任务已有运行记录，请检查原任务，不重复提交。')
    emit('video_stage',{'message':'检查现有本地生成任务与模型释放请求…'})
    release_shared(params,folder=folder,cancel=cancel)
    emit('video_stage',{'message':'准备并编码角色与动作参考（1/2）…'})
    with NativeSession(config,folder/'native_encode',cancel,emit) as server:
        motion=prepare(Path(params['motion_reference']),server.input/'motion',math.ceil(params['seconds']*24)/24,
            params.get('motion_start',0.),cancel,emit,max_side=params.get('motion_max_side',512),
            align_h3=True,repeat=params.get('motion_repeat',False),encode_video=False,save_frames=True,
            allow_tail_hold=bool(params.get('continuation_frame') or params.get('motion_allow_tail_hold')))
        expected=params.get('motion_source',{}).get('sha256')
        if expected and expected!=motion['source']['sha256']:raise ValueError('动作参考与入队记录不一致。')
        image=''
        if params.get('reference'):
            with Image.open(params['reference']) as original:
                if original.width*original.height>16_000_000:raise ValueError('角色参考图超过1600万像素，请先缩小。')
                rgba=ImageOps.exif_transpose(original).convert('RGBA')
                rgb=Image.new('RGB',rgba.size,(232,232,232));rgb.paste(rgba,mask=rgba.getchannel('A'))
                rgb.save(server.input/'character.png');image='character.png'
        compiler=compile_prompt if prompt_format==FORMAT else prompt
        text=compiler(params['prompt'],bool(image),reference_role=params.get('reference_role','appearance'),
                    reference_usage=params.get('reference_usage',''))
        if params.get('negative','').strip():text+='\nAvoid: '+params['negative'].strip()
        (folder/'prompt.txt').write_text(text,'utf-8')
        write_json(folder/'prompt-policy.json',dict(format=prompt_format,motion_timeline_clock='output',
            reference_role=params.get('reference_role','appearance'),source_video_is_editing_source=prompt_format==FORMAT))
        graph=encoding(server.info,text,params['seed'],config.get('width',768),config.get('height',1024),
                    length,'motion/frames.json',image)
        if params.get('continuation_frame'):
            from .motion_native_graph import anchor_continuation
            shutil.copyfile(params['continuation_frame'],server.input/'continuation.png')
            anchor_continuation(graph,server.info,'continuation.png')
        # This graph belongs to the private H3 server, not the shared image editor.
        write_json(folder/'workflow.json',graph)
        write_json(server.folder/'workflow.json',graph)
        def event(kind,data):
            server.check()
            if kind=='progress' and graph.get(str(data.get('node')),{}).get('class_type')!='SamplerCustomAdvanced':
                emit('video_stage',dict(message=f"处理参考或解码动画 · {data.get('value',0)}/{data.get('max',0)}"))
                return
            if kind=='executing':
                node=graph.get(str(data.get('node')),{}).get('class_type','')
                stage={'MiniMaxH3ReferenceToVideo':'正在理解角色与动作参考并编码…',
                       'UNETLoader':'正在加载专用动作参考模型…','VAEDecode':'正在解码完整动画…'}.get(node)
                if stage:emit('video_stage',dict(message=stage))
            emit(kind,data)
        try:server.client.generate(graph,server.folder/'native_result',event,cancel,allow_latent_only=True)
        except EngineUnavailable:
            if cancel.is_set():raise Cancelled('动作参考任务已取消；专用后端已停止。')
            raise
        packet=server.output_dir/'conditioning'
        if not (packet/'conditioning.json').is_file():raise ValueError('参考条件未完整保存，日志保留。')
    # Exiting the encoding process frees its CPU weights, GPU buffers and mappings.
    emit('video_stage',dict(message='参考编码已保存并释放；正在加载动画模型（2/2）…'))
    if cancel.is_set():raise Cancelled('已取消，参考条件保留。')
    write_json(folder/'stages.json',dict(encoding='completed',sampling='preparing',weights_loader='stream',encoder_process_exited=True),durable=True)
    with NativeSession(config,folder/'native_sample',cancel,emit) as server:
        shutil.copytree(packet,server.input/'conditioning')
        graph=sampling(server.info,params['seed'],config.get('width',768),config.get('height',1024),length)
        write_json(server.folder/'workflow.json',graph)
        try:result=server.client.generate(graph,server.folder/'native_result',event,cancel)
        except EngineUnavailable:
            if cancel.is_set():raise Cancelled('动作参考任务已取消；专用后端已停止。')
            raise
        paths=[Path(p) for p in result['images']]
        if len(paths)!=length:raise ValueError('生成帧数不完整，已保存结果保留，请检查 native_sample。')
    write_json(folder/'stages.json',dict(encoding='completed',sampling='completed',weights_loader='stream',encoder_process_exited=True),durable=True)
    target=folder/'animation_master.mp4'
    if not params.get('defer_exports'):encode_pngs(paths,target,24,cancel)
    return dict(video=None if params.get('defer_exports') else str(target.resolve()),native_frames=[str(p.resolve()) for p in paths],
                backend='ComfyUI/H3-Ref2VA',style_lora=False,motion=motion,staged=True,weights_loader='stream',
                frame_sha256=[digest(p) for p in paths])
