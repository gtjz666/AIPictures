"""Owned MOSS jobs, with encoder / diffusion / VAE in separate processes."""
import json,shutil,threading,time
from pathlib import Path
from PIL import Image,ImageOps
from . import moss_image as moss
from .h3_image_runtime import Session as ImageSession
from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest


class Session(ImageSession):
 node_package='aipictures_moss'
 required_nodes={'MOSSImageLayoutPrompt','TextEncodeMOSSImageEdit','AIPicturesMossSave','AIPicturesMossLoad'}
 event_prefix='moss'
 label='MOSS图片'


_verified={}


def check(cancel):
 if cancel.is_set():raise Cancelled('MOSS生成已取消，本次文件保留。')


def generate(folder,params,cancel,emit,*,research=False,session_factory=None):
 folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True);c=params['moss_settings']
 if not c.get('validated') and not research:raise ValueError('MOSS工作流尚未完成本机验证。')
 moss.validate(params['width'],params['height'],params['seed'],params['steps'],params['cfg'],params['moss_mode'],params['references'])
 if params['moss_mode']=='layout':
  moss.compile_layout(params['layout'])
  if (params['layout']['width'],params['layout']['height'])!=(params['width'],params['height']):raise ValueError('画幅与布局草稿尺寸不一致。')
 if not params['positive'].strip():raise ValueError('请填写提示词。')
 marker=folder/'moss-started.json'
 # Exclusive marker: a failed or cancelled job is never resubmitted implicitly.
 with marker.open('x',encoding='utf-8') as f:json.dump(dict(protocol=moss.PROTOCOL),f)
 check(cancel);started=time.monotonic();records=[]
 for row in c['models']:
  check(cancel);path=Path(row['path']);stamp=path.stat()
  key=(row['bytes'],row['sha256'],stamp.st_mtime_ns,stamp.st_ctime_ns)
  if stamp.st_size!=row['bytes']:raise ValueError('MOSS模型文件大小已变化。')
  if _verified.get(str(path))!=key:
   import hashlib
   sha=hashlib.sha256()
   with path.open('rb') as source:
    for block in iter(lambda:source.read(8*1024**2),b''):check(cancel);sha.update(block)
   if sha.hexdigest()!=row['sha256']:raise ValueError('MOSS模型文件校验失败。')
   _verified[str(path)]=key
  after=path.stat()
  if (after.st_size,after.st_mtime_ns)!=(stamp.st_size,stamp.st_mtime_ns):raise ValueError('模型文件在核验期间变化。')
  records.append(dict(path=str(path),sha256=row['sha256'],bytes=stamp.st_size))
 write_json(folder/'model-verification.json',records,durable=True)
 from .motion_native_backend import release_shared
 release_shared(params,folder=folder,cancel=cancel)
 session=session_factory or Session
 emit('moss_stage',dict(message='正在编码手写提示词与布局／参考图…'))
 with session(c,folder/'encode',cancel,emit) as s:
  names=[];assets=[]
  for number,row in params['references'].items():
   check(cancel);source=Path(row['path'])
   if digest(source)!=row['sha256']:raise ValueError('冻结参考图被修改。')
   name=f'reference_{len(names)+1}.png';target=s.input/name
   with Image.open(source) as image:
    rgba=ImageOps.exif_transpose(image).convert('RGBA');Image.alpha_composite(Image.new('RGBA',rgba.size,'white'),rgba).convert('RGB').save(target)
   names.append(name);assets.append(dict(slot=int(number),model_input=len(names),source_sha256=row['sha256'],prepared_sha256=digest(target)))
  write_json(folder/'inputs.json',assets,durable=True)
  s.run(moss.graph(c,params,s.info,'encode',names),latent=True);packet=s.output/'conditioning'
 emit('moss_stage',dict(message=f'编码已释放，正在生成图片 · {params["steps"]}步…'))
 with session(c,folder/'sample',cancel,emit) as s:
  shutil.copytree(packet,s.input/'conditioning');s.run(moss.graph(c,params,s.info,'sample'),latent=True);packet=s.output/'conditioning'
 emit('moss_stage',dict(message='采样已释放，正在解码图片…'))
 with session(c,folder/'decode',cancel,emit) as s:
  shutil.copytree(packet,s.input/'conditioning');result=s.run(moss.graph(c,params,s.info,'decode'))
 check(cancel)
 for row in params['references'].values():
  if digest(Path(row['path']))!=row['sha256']:raise ValueError('推理期间参考图发生变化，结果未应用。')
 images=[]
 for index,path in enumerate(result['images'],1):
  with Image.open(path) as image:
   if image.size!=(params['width'],params['height']):raise ValueError('MOSS输出画幅不一致。')
  target=folder/f'image_{index:02d}.png'
  with Path(path).open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
  images.append(str(target))
 result.update(images=images,model_family='moss_image',protocol=moss.PROTOCOL,prompt_expander=False,elapsed_seconds=time.monotonic()-started)
 write_json(folder/'result.json',result,durable=True);return result
