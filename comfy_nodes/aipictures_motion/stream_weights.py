"""Validated, per-tensor file reads. No whole-checkpoint mmap or whole-file bytes copy."""
import json
import math
import os
import struct


class StreamWeights:
    def __init__(self,path):
        self.file=open(path,'rb')
        try:
            size=os.fstat(self.file.fileno()).st_size
            raw=self.file.read(8)
            if len(raw)!=8:raise ValueError('权重文件头不完整。')
            length=struct.unpack('<Q',raw)[0]
            if not 2<=length<=100_000_000 or length+8>size:raise ValueError('权重文件头长度无效。')
            self.header=json.loads(self.file.read(length));self.offset=length+8
            if not isinstance(self.header,dict):raise ValueError('权重文件头不是对象。')
            intervals=[]
            for name,row in self.header.items():
                if name=='__metadata__':continue
                shape=row['shape'];begin,end=row['data_offsets']
                if not isinstance(shape,list) or any(type(d)!=int or d<0 for d in shape):raise ValueError('权重形状无效。')
                if type(begin)!=int or type(end)!=int or not 0<=begin<=end<=size-self.offset:
                    raise ValueError('权重数据范围越界。')
                intervals.append((begin,end))
            end=0
            for begin,finish in sorted(intervals):
                if begin!=end:raise ValueError('权重范围重叠或存在空洞。')
                end=finish
            if end!=size-self.offset:raise ValueError('权重数据长度不符。')
        except BaseException:self.file.close();raise

    def __enter__(self):return self
    def __exit__(self,*_):self.file.close()
    def keys(self):return [k for k in self.header if k!='__metadata__']
    def metadata(self):return self.header.get('__metadata__')

    def read_into(self,name,buffer,itemsize):
        row=self.header[name];begin,end=row['data_offsets']
        if math.prod(row['shape'])*itemsize!=end-begin or len(buffer)!=end-begin:
            raise ValueError('权重形状、类型与字节数不匹配：'+name)
        self.file.seek(self.offset+begin);position=0
        while position<len(buffer):
            n=self.file.readinto(buffer[position:position+8*1024*1024])
            if not n:raise ValueError('权重数据提前结束：'+name)
            position+=n


def install_stream_loader():
    """Private process opt-in; original ComfyUI and installed libraries stay untouched."""
    if os.name!='nt' or os.environ.get('AIPICTURES_STREAM_WEIGHTS')!='1':return
    import torch
    import comfy.utils as utils
    if getattr(utils.load_torch_file,'aipictures_stream',False):return
    original=utils.load_torch_file
    def load(path,safe_load=False,device=None,return_metadata=False):
        if not str(path).lower().endswith(('.safetensors','.sft')):
            return original(path,safe_load=safe_load,device=device,return_metadata=return_metadata)
        target=torch.device('cpu') if device is None else torch.device(device)
        result={}
        with StreamWeights(path) as source:
            for name in source.keys():
                row=source.header[name]
                if row['dtype'] not in utils._TYPES:raise ValueError('不支持的权重类型：'+row['dtype'])
                dtype=utils._TYPES[row['dtype']];count=row['data_offsets'][1]-row['data_offsets'][0]
                if math.prod(row['shape'])*dtype.itemsize!=count:raise ValueError('权重形状、类型与字节数不匹配：'+name)
                raw=torch.empty(count,dtype=torch.uint8,device='cpu')
                source.read_into(name,memoryview(raw.numpy()),dtype.itemsize)
                tensor=raw.view(dtype).reshape(row['shape'])
                result[name]=tensor if target.type=='cpu' else tensor.to(target)
            metadata=source.metadata()
        return (result,metadata) if return_metadata else result
    load.aipictures_stream=True;utils.load_torch_file=load
    print('AIPictures: bounded streaming weight loader active; no checkpoint mmap.',flush=True)
