"""Research-only direct H3-Image editing; exact staged tensors, no caption expander."""
import argparse,json,os,shutil,socket,subprocess,threading,time
from http.client import HTTPException
from urllib.error import URLError
from pathlib import Path
from aipictures.engine import ComfyClient,EngineUnavailable
from aipictures.owned_process import OwnedProcessJob,gated_module_command
from aipictures.storage import write_json as _write_json
from aipictures.workflow_library import digest
from aipictures.zimage import _name

def write_json(path,value):_write_json(path,value,durable=True)

class Session:
    def __init__(self,config,folder,cpu=False):self.config=config;self.folder=folder;self.cpu=cpu;self.owner=None;self.child=None;self.log=None
    def __enter__(self):
        self.folder.mkdir(parents=True,exist_ok=False)
        for n in ('input','output','user'):(self.folder/n).mkdir()
        for port in range(19200,19280):
            with socket.socket() as s:
                try:s.bind(('127.0.0.1',port));break
                except OSError:continue
        else:raise RuntimeError('No private test port available')
        self.client=ComfyClient(f'http://127.0.0.1:{port}');self.input=self.folder/'input';self.output=self.folder/'output'
        c=self.config;command=[c['python'],'-u','-m','main','--listen','127.0.0.1','--port',str(port),
          '--extra-model-paths-config',c['model_paths'],'--input-directory',str(self.input),'--output-directory',str(self.output),
          '--user-directory',str(self.folder/'user'),'--database-url','sqlite:///'+(self.folder/'user/comfyui.db').as_posix(),
          '--disable-all-custom-nodes','--whitelist-custom-nodes','aipictures_image_probe','--disable-api-nodes','--disable-auto-launch',
          '--disable-dynamic-vram','--disable-async-offload','--disable-pinned-memory','--disable-smart-memory','--cache-none']
        command+=['--cpu'] if self.cpu else ['--reserve-vram','3.0']
        write_json(self.folder/'command.json',dict(command=command,cwd=c['source'],stream_weights=True))
        self.log=(self.folder/'backend.log').open('w',encoding='utf-8')
        try:
            self.child=subprocess.Popen(gated_module_command(command,startup_trace=self.folder/'startup'),cwd=c['source'],stdin=subprocess.PIPE,
                stdout=self.log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,
                env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1',AIPICTURES_STREAM_WEIGHTS='1'))
            self.owner=OwnedProcessJob(self.child.pid);self.child.stdin.write(b'go\n');self.child.stdin.flush();self.child.stdin.close()
            write_json(self.folder/'process.json',dict(pid=self.child.pid,url=self.client.url,status='starting'))
            deadline=time.monotonic()+240
            while True:
                if self.child.poll() is not None:raise RuntimeError('Private backend exited: '+str(self.child.returncode))
                try:self.info=self.client.request('/object_info',timeout=2);break
                except (EngineUnavailable,TimeoutError,HTTPException,URLError):pass
                if time.monotonic()>deadline:raise TimeoutError('Private startup timeout')
                time.sleep(.4)
            if 'MiniMaxH3ImageConditioning' not in self.info or 'AIPicturesSaveConditioning' not in self.info:raise ValueError('Image/staging node missing')
            write_json(self.folder/'ready.json',dict(ready=True,condition_schema=self.info['MiniMaxH3ImageConditioning']))
            write_json(self.folder/'process.json',dict(pid=self.child.pid,url=self.client.url,status='ready'))
            return self
        except BaseException:self.__exit__(None,None,None);raise
    def __exit__(self,*_):
        if self.owner:self.owner.close()
        if self.child:
            if self.child.poll() is None:self.child.wait(timeout=20)
            write_json(self.folder/'process.json',dict(pid=self.child.pid,url=self.client.url,status='stopped',returncode=self.child.returncode))
        if self.log:self.log.close()
    def run(self,graph,latent=False):
        write_json(self.folder/'workflow.json',graph)
        def emit(kind,data):
            if kind in ('executing','progress'):print(self.folder.name,kind,json.dumps(data,ensure_ascii=False),flush=True)
        return self.client.generate(graph,self.folder/'result',emit,threading.Event(),allow_latent_only=latent)

def model(graph,info,config):
    graph['model']=dict(class_type='UNETLoader',inputs=dict(unet_name=_name(info,'UNETLoader','unet_name',Path(config['models'][0]['path']).name),weight_dtype='default'))

def vae(info,config):return dict(class_type='VAELoader',inputs=dict(vae_name=_name(info,'VAELoader','vae_name',Path(config['models'][1]['path']).name)))

def pid_alive(pid):
    import ctypes as c
    from ctypes import wintypes as w
    api=c.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];api.OpenProcess.restype=w.HANDLE
    api.GetExitCodeProcess.argtypes=[w.HANDLE,c.POINTER(w.DWORD)];api.GetExitCodeProcess.restype=w.BOOL
    api.CloseHandle.argtypes=[w.HANDLE];api.CloseHandle.restype=w.BOOL
    handle=api.OpenProcess(0x1000,False,int(pid))
    if not handle:
        error=c.get_last_error()
        if error==87:return False
        if error==5:return True
        raise c.WinError(error)
    try:
        code=w.DWORD()
        if not api.GetExitCodeProcess(handle,c.byref(code)):raise c.WinError(c.get_last_error())
        return code.value==259
    finally:api.CloseHandle(handle)

def reuse_encoding(previous,case):
    """Explicitly recover one interrupted private trial; never requeue a live task."""
    if (previous/'acceptance.json').exists():raise ValueError('Case already completed')
    old=json.loads((previous/'encode/workflow.json').read_text('utf-8'))['condition']['inputs']
    if any(old[k]!=case[k] for k in ('prompt','width','height')):raise ValueError('Frozen encoding request changed')
    stopped=json.loads((previous/'encode/process.json').read_text('utf-8'))
    if stopped.get('status')!='stopped' or stopped.get('returncode')!=0:raise ValueError('Encoder exit not confirmed')
    process=json.loads((previous/'sample/process.json').read_text('utf-8'))
    if pid_alive(process['pid']):raise ValueError('Recorded private sampling PID still exists; inspect it first')
    try:ComfyClient(process['url']).request('/queue',timeout=3)
    except EngineUnavailable:pass
    else:raise ValueError('Private backend is still reachable; inspect original prompt ID first')
    assets=json.loads((previous/'inputs.json').read_text('utf-8'))
    if [a['original'] for a in assets]!=case['references']:raise ValueError('Reference order changed')
    original={a['original']:a['original_sha256'] for a in assets}
    if any(digest(Path(p))!=h for p,h in original.items()) or any(digest(Path(a['actual']))!=a['actual_sha256'] for a in assets):raise ValueError('Original or encoded reference changed')
    packet=previous/'encode/output/conditioning';manifest=json.loads((packet/'conditioning.json').read_text('utf-8'))
    if manifest['tensors']!='conditioning.safetensors' or digest(packet/'conditioning.safetensors')!=manifest['sha256']:raise ValueError('Saved reference packet changed')
    return packet,assets,original

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--machine',type=Path,required=True);p.add_argument('--proof',type=Path,required=True)
    p.add_argument('--plan',type=Path);p.add_argument('--startup-only',action='store_true')
    p.add_argument('--resume-encoding',type=Path,help='One interrupted case folder; explicit new sampling attempt after proving old backend gone')
    a=p.parse_args()
    config=json.loads(a.machine.read_text('utf-8'));root=a.proof.resolve();root.mkdir(parents=True,exist_ok=False)
    if a.startup_only:
        with Session(config,root/'startup',cpu=True) as s:print('H3-Image and exact tensor staging nodes available',flush=True)
        return
    if a.plan is None:raise ValueError('A frozen plan is required')
    plan=json.loads(a.plan.read_text('utf-8'));write_json(root/'plan.json',plan)
    if a.resume_encoding and len(plan['cases'])!=1:raise ValueError('Resume requires exactly one frozen case')
    for row in config['models']:
        if Path(row['path']).stat().st_size!=row['bytes'] or digest(Path(row['path']))!=row['sha256']:raise ValueError('Model checksum mismatch')
    from tools.setup_h3_image_probe import ENCODER_SIZE,ENCODER_SHA
    encoder=Path(config['encoder']['path'])
    if encoder.stat().st_size!=ENCODER_SIZE or digest(encoder)!=ENCODER_SHA:raise ValueError('Encoder publisher checksum mismatch')
    from aipictures.motion_native_backend import release_shared
    release_shared({},folder=root,cancel=threading.Event())
    rows=[]
    for case in plan['cases']:
        folder=root/case['id'];folder.mkdir();start=time.monotonic();original={}
        from PIL import Image,ImageOps
        if a.resume_encoding:
            packet,assets,original=reuse_encoding(a.resume_encoding.resolve(),case)
            write_json(folder/'inputs.json',assets)
            write_json(folder/'resume.json',dict(source_case=str(a.resume_encoding.resolve()),encoding_manifest_sha256=digest(packet/'conditioning.json'),original_backend_not_running=True,
                note='New explicitly requested local sampling attempt after interruption; prior output is absent, original files retained.'))
        else:
          with Session(config,folder/'encode') as s:
            refs={};assets=[]
            for i,path in enumerate(case['references'],1):
                path=Path(path);original[str(path)]=digest(path);target=s.input/f'reference_{i}.png'
                with Image.open(path) as im:
                    rgba=ImageOps.exif_transpose(im).convert('RGBA')
                    rgb=Image.alpha_composite(Image.new('RGBA',rgba.size,'white'),rgba).convert('RGB');rgb.save(target)
                key=f'image_{i}';refs[f'images.image_{i}']=[key,0]
                assets.append(dict(number=i,original=str(path),original_sha256=original[str(path)],actual=str(target),actual_sha256=digest(target),preparation='original canvas; alpha composited on white; no crop/segmentation/caption'))
            graph={f'image_{i}':dict(class_type='LoadImage',inputs=dict(image=f'reference_{i}.png')) for i in range(1,len(assets)+1)}
            graph.update(clip=dict(class_type='CLIPLoader',inputs=dict(clip_name=_name(s.info,'CLIPLoader','clip_name',Path(config['encoder']['path']).name),type='minimax',device='default')),
                vae=vae(s.info,config),condition=dict(class_type='MiniMaxH3ImageConditioning',inputs=dict(clip=['clip',0],vae=['vae',0],prompt=case['prompt'],width=case['width'],height=case['height'],**refs)),
                checkpoint=dict(class_type='AIPicturesSaveConditioning',inputs=dict(conditioning=['condition',0],latent=['condition',1])))
            write_json(folder/'inputs.json',assets);s.run(graph,True);packet=s.output/'conditioning'
            if not (packet/'conditioning.json').is_file():raise ValueError('Reference packet missing')
        encode_seconds=time.monotonic()-start;write_json(folder/'stages.json',dict(encoding='completed',encoder_process_exited=True))
        with Session(config,folder/'sample') as s:
            shutil.copytree(packet,s.input/'conditioning')
            graph=dict(condition=dict(class_type='AIPicturesLoadConditioning',inputs=dict(manifest='conditioning/conditioning.json')))
            model(graph,s.info,config)
            graph.update(negative=dict(class_type='ConditioningZeroOut',inputs=dict(conditioning=['condition',0])),
                sample=dict(class_type='KSampler',inputs=dict(model=['model',0],positive=['condition',0],negative=['negative',0],latent_image=['condition',1],seed=case['seed'],steps=6,cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.)),
                checkpoint=dict(class_type='AIPicturesSaveConditioning',inputs=dict(conditioning=['condition',0],latent=['sample',0])))
            s.run(graph,True);sampled=s.output/'conditioning'
        sample_seconds=time.monotonic()-start-encode_seconds
        with Session(config,folder/'decode') as s:
            shutil.copytree(sampled,s.input/'conditioning')
            graph=dict(condition=dict(class_type='AIPicturesLoadConditioning',inputs=dict(manifest='conditioning/conditioning.json')),
                vae=vae(s.info,config),decode=dict(class_type='VAEDecode',inputs=dict(samples=['condition',1],vae=['vae',0])),
                save=dict(class_type='SaveImage',inputs=dict(images=['decode',0],filename_prefix=case['id'])))
            result=s.run(graph)
        if any(digest(Path(path))!=sha for path,sha in original.items()):raise ValueError('Original input changed')
        with Image.open(result['images'][0]) as im:
            if im.size!=(case['width'],case['height']):raise ValueError('Wrong output canvas')
        row=dict(case=case['id'],result=result,elapsed_seconds=time.monotonic()-start,encoding_seconds=encode_seconds,sampling_seconds=sample_seconds,
            original_hashes=original,prompt_expander=False,reference_count=len(case['references']),encoding_reused=bool(a.resume_encoding),
            elapsed_excludes_prior_encoding=bool(a.resume_encoding),quality_review='pending; execution completion is not visual acceptance')
        write_json(folder/'acceptance.json',row);rows.append(row);write_json(root/'results.json',rows)
        print('CASE COMPLETED',case['id'],round(row['elapsed_seconds'],2),flush=True)

if __name__=='__main__':main()
