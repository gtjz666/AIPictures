"""Foreground-only identity conditioning, with owned CPU lifetime and content cache."""
import hashlib,json,os,subprocess,sys,time
from functools import lru_cache
from pathlib import Path
from uuid import uuid4
from PIL import Image,ImageOps

VERSION=1


def settings(data):
    try:
        value=json.loads((Path(data)/'background-settings.json').read_text('utf-8'))
        if value['model']!='birefnet-general':return None
        path=Path(value['root'])/'models/birefnet-general/birefnet-general.onnx'
        if not path.is_file():return None
        return dict(model=value['model'],root=str(Path(value['root']).resolve()),path=str(path.resolve()))
    except (OSError,KeyError,ValueError,TypeError):return None


@lru_cache(maxsize=4)
def model_digest(path,size,mtime):
    from .workflow_library import digest
    return digest(Path(path))


def prepare(source,data,config,cancel,emit):
    from .engine import Cancelled
    from .owned_process import OwnedProcessJob
    from .storage import write_json
    from .workflow_library import digest
    if cancel.is_set():raise Cancelled('主体准备已取消。')
    source=Path(source);sha=digest(source)
    with Image.open(source) as im:
        alpha=im.convert('RGBA').getchannel('A')
        transparent=sum(alpha.histogram()[:16])>im.width*im.height*.01
    model_sha=None
    if not transparent:
        if not config:raise ValueError('排除主体原场景需要已安装的BiRefNet。也可取消“仅借用主体外观”。')
        model=Path(config['path']);stat=model.stat();model_sha=model_digest(str(model),stat.st_size,stat.st_mtime_ns)
    if cancel.is_set():raise Cancelled('主体准备已取消。')
    key=hashlib.sha256(json.dumps(dict(version=VERSION,source=sha,model=model_sha),sort_keys=True).encode()).hexdigest()
    cache=Path(data)/'reference-preparation';cache.mkdir(parents=True,exist_ok=True)
    record=cache/(key+'.json');target=cache/(key+'.png')
    if record.is_file():
        value=json.loads(record.read_text('utf-8'))
        if value['source_sha256']!=sha or digest(target)!=value['prepared_sha256']:raise ValueError('主体准备缓存校验失败，未提交生成。')
        if cancel.is_set():raise Cancelled('主体准备已取消。')
        return dict(value,source=str(source.resolve()),prepared=str(target.resolve()),cache_hit=True)
    work=cache/'work'/uuid4().hex;work.mkdir(parents=True,exist_ok=False)
    request=work/'request.json';log=work/'worker.log'
    write_json(request,dict(source=str(source.resolve()),source_sha256=sha,output=str(work.resolve()),transparent=transparent,
        model=config,model_sha256=model_sha,version=VERSION))
    emit('intent_stage',dict(message='正在排除主体参考中的原场景干扰…'))
    owner=None
    with log.open('w',encoding='utf-8') as output:
        child=subprocess.Popen([sys.executable,'-u','-m','aipictures.reference_subject',str(request.resolve())],cwd=Path(__file__).resolve().parent.parent,
            stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        try:
            owner=OwnedProcessJob(child.pid)
            while child.poll() is None:
                if cancel.wait(.15):raise Cancelled('主体准备已取消。')
        finally:
            if owner:owner.close()
            if child.poll() is None:child.terminate();child.wait(timeout=15)
    if cancel.is_set():raise Cancelled('主体准备已取消。')
    if child.returncode:raise ValueError('主体准备失败，原图保留；请查看本次主体准备日志。')
    value=json.loads((work/'result.json').read_text('utf-8'))
    if digest(source)!=sha or value['source_sha256']!=sha:raise ValueError('主体参考在准备期间发生变化。')
    prepared=Path(value['prepared'])
    if digest(prepared)!=value['prepared_sha256']:raise ValueError('主体准备输出校验失败。')
    temporary=target.with_suffix('.'+uuid4().hex+'.tmp')
    temporary.write_bytes(prepared.read_bytes());os.replace(temporary,target)
    value.update(prepared=str(target.resolve()),worker_returncode=child.returncode,worker_result=str(work/'result.json'),cache_hit=False)
    write_json(record,value)
    return value


def run(request):
    os.environ['CUDA_VISIBLE_DEVICES']='-1'
    from .storage import write_json
    from .workflow_library import digest
    source=Path(request['source']);output=Path(request['output']);started=time.monotonic()
    if digest(source)!=request['source_sha256']:raise ValueError('Source hash changed')
    with Image.open(source) as im:rgba=ImageOps.exif_transpose(im).convert('RGBA')
    if request['transparent']:
        mask=rgba.getchannel('A');method='original_alpha'
    else:
        config=request['model']
        if digest(Path(config['path']))!=request['model_sha256']:raise ValueError('Segmentation model changed')
        from .background import create_session
        from rembg import remove
        session=create_session(config['model'],Path(config['root']))
        mask=remove(rgba.convert('RGB'),session=session,only_mask=True).convert('L');method=config['model']
    bounds=mask.point(lambda a:255 if a>128 else 0).getbbox()
    if not bounds:raise ValueError('主体没有可靠的前景区域，请取消“仅借用主体外观”后核对素材。')
    coverage=sum(mask.histogram()[129:])/(rgba.width*rgba.height)
    if not request['transparent'] and not .01<coverage<.99:raise ValueError('主体分离结果异常，未使用完整场景替代。')
    mask.save(output/'mask.png');rgba.putalpha(mask);cutout=rgba.crop(bounds);cutout.save(output/'cutout.png')
    rgb=Image.new('RGB',cutout.size,'white');rgb.paste(cutout,mask=cutout.getchannel('A'));rgb.save(output/'subject.png')
    if digest(source)!=request['source_sha256']:raise ValueError('Source changed during preparation')
    value=dict(source=str(source),source_sha256=request['source_sha256'],prepared=str(output/'subject.png'),prepared_sha256=digest(output/'subject.png'),
        model_sha256=request['model_sha256'],version=request['version'],method=method,bounds=list(bounds),coverage=coverage,
        elapsed_seconds=time.monotonic()-started,device='cpu',original_preserved=True)
    write_json(output/'result.json',value);print(json.dumps(value),flush=True)


if __name__=='__main__':run(json.loads(Path(sys.argv[1]).read_text('utf-8')))
