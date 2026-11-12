"""Prepare transparent export frames in an owned CPU process; preserve source RGB."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
from uuid import uuid4
from PIL import Image
from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest

VERSION=1

def has_alpha(path):
    with Image.open(path) as im:
        h=im.convert('RGBA').getchannel('A').histogram()
        return sum(h[:16])>im.width*im.height*.01 and sum(h[64:])>100

def prepare(manifest,cancel,emit):
    from .video_io import prepare_export_frames
    from .selected_frames import read_source
    from .background import MODEL,MODEL_ROOT,model_file
    from .reference_subject import model_digest
    from .owned_process import OwnedProcessJob,gated_module_command
    if cancel.is_set():raise Cancelled('透明导出准备已取消。')
    manifest=Path(manifest).resolve()
    prepare_export_frames(manifest,cancel,emit)
    data,paths=read_source(manifest)
    if data.get('export_background') or all(has_alpha(p) for p in paths):return str(manifest)
    model=model_file()
    if not model.is_file():raise ValueError('透明导出需要已安装的本地去背景模型，原动画保留。')
    stat=model.stat();model_sha=model_digest(str(model),stat.st_size,stat.st_mtime_ns)
    assets=[dict(path=str(p),sha256=digest(p)) for p in paths]
    source_sha=digest(manifest)
    key=hashlib.sha256(json.dumps(dict(version=VERSION,source=source_sha,images=assets,model=model_sha),sort_keys=True).encode()).hexdigest()
    cache=manifest.parent/'export_background';cache.mkdir(exist_ok=True)
    index=cache/(key+'.json')
    if index.is_file():
        ready=json.loads(index.read_text('utf-8'))
        if all(Path(p).is_file() and digest(Path(p))==sha for p,sha in ready['files'].items()):
            if cancel.is_set():raise Cancelled('透明导出准备已取消。')
            return ready['manifest']
        raise ValueError('透明导出缓存校验失败，原动画保留。')
    folder=cache/uuid4().hex;folder.mkdir();request=folder/'request.json'
    write_json(request,dict(source_manifest=str(manifest),source_sha256=source_sha,data=data,assets=assets,
        folder=str(folder),model=MODEL,root=str(MODEL_ROOT),model_sha256=model_sha))
    owner=None;child=None;last=-1
    emit('video_stage',dict(message='正在准备透明动画帧…'))
    with (folder/'worker.log').open('w',encoding='utf-8') as log:
        try:
            child=subprocess.Popen(gated_module_command([sys.executable,'-u','-m','aipictures.export_background',str(request)]),
                cwd=Path(__file__).resolve().parent.parent,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,
                env=dict(os.environ,CUDA_VISIBLE_DEVICES='-1',PYTHONUTF8='1'),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            owner=OwnedProcessJob(child.pid);child.stdin.write(b'go\n');child.stdin.flush();child.stdin.close()
            while child.poll() is None:
                if cancel.wait(.15):raise Cancelled('透明导出准备已取消，原动画保留。')
                try:progress=json.loads((folder/'progress.json').read_text('utf-8'))
                except (OSError,ValueError):continue
                if progress['value']!=last:
                    last=progress['value'];emit('video_export_progress',progress)
                    emit('video_stage',dict(message=f'准备透明动画帧 · {last}/{len(paths)}'))
        finally:
            if child and child.stdin and not child.stdin.closed:child.stdin.close()
            if owner:owner.close()
            if child and child.poll() is None:child.wait(timeout=20)
    if cancel.is_set():raise Cancelled('透明导出准备已取消，原动画保留。')
    if child.returncode:raise ValueError('透明导出准备失败，原动画保留；请查看本次导出日志。')
    if digest(manifest)!=source_sha or any(digest(Path(a['path']))!=a['sha256'] for a in assets):raise ValueError('原动画在处理期间已变化，未打开旧导出结果。')
    ready=json.loads((folder/'result.json').read_text('utf-8'));ready['worker_exited']=True
    write_json(index,ready)
    return ready['manifest']

def run(request):
    from . import background
    from PIL.PngImagePlugin import PngInfo
    import threading
    folder=Path(request['folder']);model=background.model_file(request['model'],request['root'])
    if digest(model)!=request['model_sha256']:raise ValueError('Background model changed')
    background.MODEL=request['model'];background.MODEL_ROOT=Path(request['root'])
    frames=[];files={};data=request['data'];raw=[]
    try:
        for i,asset in enumerate(request['assets']):
            source=Path(asset['path'])
            if digest(source)!=asset['sha256']:raise ValueError('Source frame changed')
            with Image.open(source) as im:
                before=im.convert('RGB').tobytes();info=PngInfo()
                for key,value in im.info.items():
                    if isinstance(value,str):info.add_text(key,value)
                out=background.foreground_rgba(im,threading.Event(),anti_alias=False)
                if out.size!=im.size or out.convert('RGB').tobytes()!=before:raise ValueError('RGB or canvas changed')
                target=folder/f'frame_{i:05d}.png';out.save(target,pnginfo=info)
            if digest(source)!=asset['sha256']:raise ValueError('Source frame changed')
            frames.append(dict(data['frames'][i],image=target.name))
            raw.append(dict(data['frames'][i],image=str(source)))
            files[str(target)]=digest(target);write_json(folder/'progress.json',dict(value=i+1,max=len(request['assets'])))
        result=dict(data,frames=frames,original_frames=raw,source_manifest=request['source_manifest'],
            export_background=dict(transparent=True,model=request['model'],model_sha256=request['model_sha256'],device='cpu',rgb_preserved=True))
        result.pop('exports',None)
        target=folder/'sequence.json';write_json(target,result);files[str(target)]=digest(target)
        write_json(folder/'result.json',dict(manifest=str(target),files=files,worker_pid=os.getpid()))
    finally:background.release_session()

if __name__=='__main__':run(json.loads(Path(sys.argv[1]).read_text('utf-8')))
