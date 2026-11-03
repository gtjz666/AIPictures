"""Safe exact conditioning checkpoint, retaining all reference tensors and nested AV latent."""
import hashlib
import json
import math
from pathlib import Path
import torch
from safetensors.torch import save_file,load_file
from comfy.nested_tensor import NestedTensor
import folder_paths


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def save_packet(conditioning,latent,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);tensors={}
    def pack(value):
        if isinstance(value,NestedTensor):return dict(type='nested',items=[pack(x) for x in value.unbind()])
        if isinstance(value,torch.Tensor):
            name=f't{len(tensors):05d}';tensors[name]=value.detach().cpu().contiguous().clone()
            return dict(type='tensor',name=name)
        if isinstance(value,(list,tuple)):return dict(type='tuple' if isinstance(value,tuple) else 'list',items=[pack(x) for x in value])
        if isinstance(value,dict):return dict(type='dict',items=[[pack(k),pack(v)] for k,v in value.items()])
        if value is None or type(value) in (bool,int,str) or type(value)==float and math.isfinite(value):return dict(type='value',value=value)
        raise ValueError('参考条件含不支持的对象：'+type(value).__name__)
    tree=pack(dict(conditioning=conditioning,latent=latent))
    target=folder/'conditioning.safetensors';save_file(tensors,str(target))
    checksum=digest(target)
    manifest=folder/'conditioning.json';manifest.write_text(json.dumps(dict(schema_version=1,tensors=target.name,sha256=checksum,tree=tree)),'utf-8')
    return manifest


def load_packet(manifest):
    manifest=Path(manifest);data=json.loads(manifest.read_text('utf-8'))
    if data.get('schema_version')!=1 or data.get('tensors')!='conditioning.safetensors':raise ValueError('参考条件清单无效。')
    target=manifest.parent/data['tensors']
    if digest(target)!=data['sha256']:raise ValueError('参考条件被修改，停止采样。')
    tensors=load_file(str(target),device='cpu',backend='pread')
    def unpack(row):
        kind=row['type']
        if kind=='tensor':return tensors[row['name']]
        if kind=='nested':return NestedTensor([unpack(x) for x in row['items']])
        if kind=='dict':return {unpack(k):unpack(v) for k,v in row['items']}
        if kind in ('list','tuple'):
            items=[unpack(x) for x in row['items']];return tuple(items) if kind=='tuple' else items
        if kind=='value':return row['value']
        raise ValueError('参考条件类型无效。')
    value=unpack(data['tree']);return value['conditioning'],value['latent']


class SaveConditioning:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'conditioning':('CONDITIONING',),'latent':('LATENT',)}}
    RETURN_TYPES=();FUNCTION='save';OUTPUT_NODE=True;CATEGORY='AIPictures/motion'
    def save(self,conditioning,latent):
        root=Path(folder_paths.get_output_directory());manifest=save_packet(conditioning,latent,root/'conditioning')
        return {'ui':{'latents':[dict(filename=n,subfolder='conditioning',type='output')
                                  for n in ('conditioning.safetensors','conditioning.json')]}}


class LoadConditioning:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'manifest':('STRING',{'default':'conditioning/conditioning.json'})}}
    RETURN_TYPES=('CONDITIONING','LATENT');FUNCTION='load';CATEGORY='AIPictures/motion'
    def load(self,manifest):
        root=Path(folder_paths.get_input_directory()).resolve();path=(root/manifest).resolve(strict=True)
        if not path.is_relative_to(root):raise ValueError('条件文件不在本次任务目录中。')
        return load_packet(path)
