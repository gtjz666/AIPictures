"""Manual MOSS layout / edit contracts. No prompt expansion or visual captioner."""
import json,math
from pathlib import Path
from .multi_reference import bind_text

PROTOCOL='moss_native_staged_v1'
MODEL='moss_image_sft_int8_convrot.safetensors'
ENCODER='qwen3.5_9b_w4a8_gptq.safetensors'
VAE='flux2-vae_small.safetensors'
LORA='moss_image_edit_lora_rank_64_bf16.safetensors'


def settings(data):
 try:
  c=json.loads((Path(data)/'moss-image-settings.json').read_text('utf-8'))
  if not c.get('validated') or not all(Path(c[k]).is_file() for k in ['python','model_paths']):return {}
  if not (Path(c['source'])/'main.py').is_file():return {}
  if {Path(r['path']).name for r in c['models']}!={MODEL,ENCODER,VAE,LORA}:return {}
  if any(Path(r['path']).stat().st_size!=r['bytes'] or not r.get('sha256') for r in c['models']):return {}
  return c
 except (OSError,KeyError,TypeError,ValueError,AttributeError):return {}


def validate(width,height,seed,steps,cfg,mode,references):
 if type(width)!=int or type(height)!=int or min(width,height)<256 or max(width,height)>4096 or width%16 or height%16 or not 262144<=width*height<=2097152:
  raise ValueError('MOSS首版画幅须为16的倍数，约26万至200万像素。')
 if type(seed)!=int or not 0<=seed<2**64 or type(steps)!=int or not 1<=steps<=100 or not math.isfinite(cfg) or not 1<=cfg<=10:raise ValueError('种子、步数或引导参数无效。')
 if mode=='edit' and width*height>1100000:raise ValueError('本机参考编辑首版输出限约110万像素，排版生成可到200万。')
 if mode not in ['layout','edit']:raise ValueError('未知MOSS模式。')
 if mode=='layout' and references:raise ValueError('布局生成不接参考图；请切换参考图编辑。')
 if mode=='edit' and (not 1<=len(references)<=4 or any(type(n)!=int or not 1<=n<=4 for n in references)):raise ValueError('参考编辑需要1至4张编号图片。')


def compile_layout(draft):
 """Top-left pixel xyxy -> enclosing centre-origin pixel yxyx, per OpenMOSS."""
 if not isinstance(draft,dict) or draft.get('bbox_coord_space')!='abs' or draft.get('bbox_format')!='xyxy':raise ValueError('草稿需为左上角像素坐标abs／xyxy。')
 w,h=draft.get('width'),draft.get('height');validate(w,h,0,25,2.5,'layout',{})
 caption=draft.get('summary',{}).get('caption','')
 if not isinstance(caption,str) or not caption.strip() or len(caption)>16000:raise ValueError('请填写画面整体提示词。')
 rows=draft.get('items',[])
 if not isinstance(rows,list) or len(rows)>32:raise ValueError('最多32个布局元素。')
 items=[]
 for row in rows:
  if not isinstance(row,dict) or row.get('label') not in ['text','object','character']:raise ValueError('元素类型无效。')
  box=row.get('bbox');text=row.get('text','');desc=row.get('caption','')
  if not isinstance(box,list) or len(box)!=4 or any(type(x) not in [float,int] or not math.isfinite(x) for x in box):raise ValueError('区域坐标无效。')
  x0,y0,x1,y1=box
  if not 0<=x0<x1<=w or not 0<=y0<y1<=h:raise ValueError('布局区域需位于画布内且不能为空。')
  if not isinstance(desc,str) or len(desc)>4000 or not isinstance(text,str) or len(text)>4000:raise ValueError('元素文字或说明过长。')
  if row['label']=='text' and not text:raise ValueError('文字区域需要填写要显示的文字。')
  item=dict(label=row['label'],caption=desc,bbox=[math.floor(y0)-h//2,math.floor(x0)-w//2,math.ceil(y1)-h//2,math.ceil(x1)-w//2])
  if row['label']=='text':item['text']=text
  items.append(item)
 if not items:return caption
 return json.dumps(dict(summary=dict(caption=caption),items=items,bbox_coord_space='abs_centralized',bbox_format='yxyx'),ensure_ascii=False,separators=(',',':'))


def draft(width=1024,height=1024):
 return dict(width=width,height=height,bbox_coord_space='abs',bbox_format='xyxy',summary=dict(caption='游戏主菜单，深蓝色奇幻星空背景，金色清晰标题，中间一颗发光蓝色宝石，下方一个开始按钮。'),items=[
  dict(label='text',text='星界远征',caption='顶部居中的大号金色中文标题',bbox=[96,80,928,240]),
  dict(label='object',caption='一颗独立的发光蓝色水晶宝石，无人物',bbox=[288,288,736,688]),
  dict(label='text',text='开始游戏',caption='下方居中，清晰白色中文按钮文字',bbox=[288,784,736,928])])


def model_name(config,filename,node,field,info):
 if info:
  from .zimage import _name
  return _name(info,node,field,filename)
 return filename


def graph(config,params,info=None,stage='full',names=()):
 """Flat API graph; official native node families, no enhancer subgraphs."""
 def name(f,n,k):return model_name(config,f,n,k,info)
 mode=params['moss_mode'];g={}
 if stage in ['encode','full']:
  g['clip']=dict(class_type='CLIPLoader',inputs=dict(clip_name=name(ENCODER,'CLIPLoader','clip_name'),type='moss_image',device='default'))
  g['latent']=dict(class_type='EmptyFlux2LatentImage',inputs=dict(width=params['width'],height=params['height'],batch_size=1))
  if mode=='edit':
   g['vae']=dict(class_type='VAELoader',inputs=dict(vae_name=name(VAE,'VAELoader','vae_name')))
   for i,n in enumerate(names,1):
    g[f'image{i}']=dict(class_type='LoadImage',inputs=dict(image=n))
    g[f'scale{i}']=dict(class_type='ImageScaleToTotalPixels',inputs=dict(image=[f'image{i}',0],upscale_method='lanczos',megapixels=1.0/max(1,len(names)),resolution_steps=16))
   prompt=bind_text(params['positive'],list(params.get('references',{})),label='Image')
   for key,text in [('positive',prompt),('negative',params.get('negative',''))]:
    g[key]=dict(class_type='TextEncodeMOSSImageEdit',inputs=dict(clip=['clip',0],vae=['vae',0],prompt=text,edit_format='Moss-Image-Edit',image_strength=1.0,**{f'images.image_{i-1}':[f'scale{i}',0] for i in range(1,len(names)+1)}))
  else:
   for key,text in [('positive',compile_layout(params['layout'])),('negative',params.get('negative',''))]:g[key]=dict(class_type='CLIPTextEncode',inputs=dict(clip=['clip',0],text=text))
  pos,neg,latent=['positive',0],['negative',0],['latent',0]
  if stage=='encode':g['save']=dict(class_type='AIPicturesMossSave',inputs=dict(positive=pos,negative=neg,latent=latent));return g
 else:
  g['condition']=dict(class_type='AIPicturesMossLoad',inputs=dict(manifest='conditioning/conditioning.json'))
  pos,neg,latent=['condition',0],['condition',1],['condition',2]
 if stage in ['sample','full']:
  g['model']=dict(class_type='UNETLoader',inputs=dict(unet_name=name(MODEL,'UNETLoader','unet_name'),weight_dtype='default'))
  model=['model',0]
  if mode=='edit':
   g['edit_lora']=dict(class_type='LoraLoaderModelOnly',inputs=dict(model=model,lora_name=name(LORA,'LoraLoaderModelOnly','lora_name'),strength_model=1.0));model=['edit_lora',0]
  g['slg']=dict(class_type='SkipLayerGuidanceDiTSimple',inputs=dict(model=model,double_layers='',single_layers='22',start_percent=0.,end_percent=1. if mode=='edit' else .5))
  g['sample']=dict(class_type='KSampler',inputs=dict(model=['slg',0],positive=pos,negative=neg,latent_image=latent,seed=params['seed'],steps=params['steps'],cfg=params['cfg'],sampler_name='euler' if mode=='edit' else 'er_sde',scheduler='normal' if mode=='edit' else 'simple',denoise=1.))
  latent=['sample',0]
  if stage=='sample':g['save']=dict(class_type='AIPicturesMossSave',inputs=dict(positive=pos,negative=neg,latent=latent));return g
 if 'vae' not in g:g['vae']=dict(class_type='VAELoader',inputs=dict(vae_name=name(VAE,'VAELoader','vae_name')))
 g['decode']=dict(class_type='VAEDecode',inputs=dict(samples=latent,vae=['vae',0]))
 g['save']=dict(class_type='SaveImage',inputs=dict(images=['decode',0],filename_prefix='MOSS_'+mode))
 return g
