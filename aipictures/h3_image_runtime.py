"""Owned, cancellable H3 Image stages. No shared backend or prompt expansion."""
import os
import shutil
import socket
import subprocess
import threading
import time
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from PIL import Image,ImageOps
from .engine import ComfyClient,EngineUnavailable,Cancelled
from .owned_process import OwnedProcessJob,gated_module_command
from .storage import write_json
from .workflow_library import digest
from . import h3_image as h3

_verified={}


def verify_models(config,folder,cancel):
    records=[]
    receipts={row['path']:row for row in config.get('verified_models',[])}
    for row in config['models']+[config['encoder']]:
        check(cancel);path=Path(row['path']);stat=path.stat()
        stamp=dict(path=str(path),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,ctime_ns=stat.st_ctime_ns,sha256=row['sha256'])
        key=tuple(stamp.values())
        if stat.st_size!=row['bytes']:raise ValueError('H3模型大小已变化，未开始推理。')
        if _verified.get(str(path))!=key and receipts.get(str(path))!=stamp:
            if digest(path)!=row['sha256']:raise ValueError('H3图片模型校验失败，未开始推理。')
            after=path.stat()
            if (after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=(stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns):raise ValueError('模型校验期间文件变化。')
        _verified[str(path)]=key;records.append(stamp)
    write_json(Path(folder)/'model-verification.json',records,durable=True)
    return records


def check(cancel):
    if cancel.is_set():raise Cancelled('H3图片生成已取消，原素材和已完成阶段保留。')


class Session:
    def __init__(self,config,folder,cancel,emit):
        self.config=config;self.folder=Path(folder);self.cancel=cancel;self.emit=emit
        self.owner=self.child=self.log=None;self.stop=threading.Event();self.watcher=None

    def __enter__(self):
        check(self.cancel);self.folder.mkdir(parents=True,exist_ok=False)
        for n in ('input','output','user'):(self.folder/n).mkdir()
        self.input=self.folder/'input';self.output=self.folder/'output'
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        self.client=ComfyClient(f'http://127.0.0.1:{port}');c=self.config
        command=[c['python'],'-u','-m','main','--listen','127.0.0.1','--port',str(port),
            '--extra-model-paths-config',c['model_paths'],'--input-directory',str(self.input),'--output-directory',str(self.output),
            '--user-directory',str(self.folder/'user'),'--database-url','sqlite:///'+(self.folder/'user/comfyui.db').as_posix(),
            '--disable-all-custom-nodes','--whitelist-custom-nodes','aipictures_image_probe','--disable-api-nodes','--disable-auto-launch',
            '--disable-dynamic-vram','--disable-async-offload','--disable-pinned-memory','--disable-smart-memory','--cache-none','--reserve-vram','3.0']
        write_json(self.folder/'command.json',dict(command=command,cwd=c['source'],stream_weights=True),durable=True)
        self.log=(self.folder/'backend.log').open('w',encoding='utf-8')
        try:
            self.child=subprocess.Popen(gated_module_command(command,startup_trace=self.folder/'startup'),cwd=c['source'],stdin=subprocess.PIPE,
                stdout=self.log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1',AIPICTURES_STREAM_WEIGHTS='1'))
            self.owner=OwnedProcessJob(self.child.pid)
            self.emit('h3_image_process',dict(pid=self.child.pid,owner=self.owner))
            self.child.stdin.write(b'go\n');self.child.stdin.flush();self.child.stdin.close()
            def watch():
                while not self.stop.wait(.2):
                    if self.cancel.is_set():self.owner.close();return
            self.watcher=threading.Thread(target=watch,daemon=True);self.watcher.start()
            write_json(self.folder/'process.json',dict(pid=self.child.pid,url=self.client.url,status='starting'),durable=True)
            deadline=time.monotonic()+240
            while True:
                check(self.cancel)
                if self.child.poll() is not None:raise RuntimeError('H3图片引擎启动失败，请查看本次backend.log。')
                try:self.info=self.client.request('/object_info',timeout=2);break
                except (EngineUnavailable,TimeoutError,HTTPException,URLError):pass
                if time.monotonic()>deadline:raise TimeoutError('H3图片引擎启动超时。')
                self.cancel.wait(.4)
            required={'MiniMaxH3ImageConditioning','AIPicturesSaveConditioning','AIPicturesLoadConditioning'}
            if required-set(self.info):raise ValueError('H3图片或张量保存节点缺失；没有切换其他模型。')
            return self
        except BaseException:self.__exit__(None,None,None);raise

    def __exit__(self,*_):
        self.stop.set()
        if self.owner:self.owner.close()
        if self.watcher:self.watcher.join(timeout=1)
        if self.child:
            if self.child.poll() is None:self.child.wait(timeout=20)
            write_json(self.folder/'process.json',dict(pid=self.child.pid,url=self.client.url,status='stopped',returncode=self.child.returncode),durable=True)
        if self.log:self.log.close()

    def run(self,graph,*,latent=False):
        check(self.cancel);write_json(self.folder/'workflow.json',graph,durable=True)
        return self.client.generate(graph,self.folder/'result',self.emit,self.cancel,allow_latent_only=latent)


def generate(folder,params,cancel,emit):
    folder=Path(folder);check(cancel)
    if (folder/'h3-image-started.json').exists():raise ValueError('本任务已经提交过，请先检查原记录；不会重复生成。')
    c=params['h3_image_settings']
    if not c.get('validated'):raise ValueError('H3图片配置尚未通过本机验收。')
    h3.validate(params['width'],params['height'],params['seed'],params['references'])
    write_json(folder/'h3-image-started.json',dict(protocol=h3.PROTOCOL),durable=True)
    start=time.monotonic()
    try:
        emit('h3_image_stage',dict(message='正在核验图片模型与冻结参考图…'))
        verify_models(c,folder,cancel)
        for row in params['references'].values():
            if digest(Path(row['path']))!=row['sha256']:raise ValueError('本次参考图已变化，未开始推理。')
        from .motion_native_backend import release_shared
        release_shared(params,folder=folder,cancel=cancel)
        emit('h3_image_stage',dict(message='正在编码提示词与参考图…'))
        with Session(c,folder/'encode',cancel,emit) as s:
            names=[];assets=[]
            for number,row in params['references'].items():
                check(cancel);path=Path(row['path']);name=f'reference_{len(names)+1}.png';target=s.input/name
                with Image.open(path) as im:
                    rgba=ImageOps.exif_transpose(im).convert('RGBA')
                    Image.alpha_composite(Image.new('RGBA',rgba.size,'white'),rgba).convert('RGB').save(target)
                names.append(name);assets.append(dict(slot=int(number),model_input=len(names),path=str(target),sha256=digest(target),source_sha256=row['sha256']))
            write_json(folder/'inputs.json',assets,durable=True)
            s.run(h3.encode_graph(c,params['positive'],params['width'],params['height'],names,s.info),latent=True)
            packet=s.output/'conditioning'
        emit('h3_image_stage',dict(message='参考编码已释放，正在生成图片 · 6步…'))
        with Session(c,folder/'sample',cancel,emit) as s:
            shutil.copytree(packet,s.input/'conditioning')
            s.run(h3.sample_graph(c,params['seed'],s.info),latent=True);sampled=s.output/'conditioning'
        emit('h3_image_stage',dict(message='采样已释放，正在解码图片…'))
        with Session(c,folder/'decode',cancel,emit) as s:
            shutil.copytree(sampled,s.input/'conditioning');result=s.run(h3.decode_graph(c,s.info))
        check(cancel)
        for row in params['references'].values():
            if digest(Path(row['path']))!=row['sha256']:raise ValueError('参考图在推理期间被修改，结果未应用。')
        with Image.open(result['images'][0]) as im:
            if im.size!=(params['width'],params['height']):raise ValueError('H3输出画幅不一致。')
        originals=list(result['images']);images=[]
        for i,path in enumerate(originals,1):
            target=folder/f'image_{i:02d}.png'
            if target.exists():raise ValueError('本次成品路径已存在，不会覆盖。')
            shutil.copyfile(path,target);images.append(str(target))
        result.update(images=images,raw_images=originals)
        from .general_image import finish_output
        result=finish_output(result,folder,emit,cancel,transparent=params.get('output_background')=='transparent')
        result.update(model_family='h3_image',protocol=h3.PROTOCOL,elapsed_seconds=time.monotonic()-start,prompt_expander=False)
        write_json(folder/'result.json',result,durable=True);return result
    except BaseException:
        check(cancel);raise
