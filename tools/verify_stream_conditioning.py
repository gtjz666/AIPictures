"""Real CPU tensor fidelity check using the isolated H3 runtime, no GPU or model generation."""
import importlib.util
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
import torch
from safetensors.torch import save_file


def main():
    root=Path(__file__).resolve().parents[1];node=root/'comfy_nodes/aipictures_motion'
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--comfy-root',type=Path)
    args=parser.parse_args()
    source=args.comfy_root or Path(json.loads((root/'data/motion-native-settings.json').read_text('utf-8'))['source'])
    sys.path.insert(0,str(source))
    import comfy
    from comfy.nested_tensor import NestedTensor
    fake=ModuleType('comfy.utils');fake._TYPES={
        'F32':torch.float32,'F16':torch.float16,'BF16':torch.bfloat16,'I8':torch.int8,'U8':torch.uint8,
        'BOOL':torch.bool,'I64':torch.int64,'F8_E4M3':torch.float8_e4m3fn,'F8_E5M2':torch.float8_e5m2}
    fake.load_torch_file=lambda *a,**k:None;sys.modules['comfy.utils']=fake;comfy.utils=fake
    spec=importlib.util.spec_from_file_location('stream_weights_real',node/'stream_weights.py')
    stream=importlib.util.module_from_spec(spec);spec.loader.exec_module(stream)
    os.environ['AIPICTURES_STREAM_WEIGHTS']='1';stream.install_stream_loader()
    folder_paths=ModuleType('folder_paths');sys.modules['folder_paths']=folder_paths
    spec=importlib.util.spec_from_file_location('conditioning_real',node/'conditioning.py')
    packet=importlib.util.module_from_spec(spec);spec.loader.exec_module(packet)
    def equal(a,b):
        if isinstance(a,NestedTensor):return isinstance(b,NestedTensor) and all(equal(x,y) for x,y in zip(a.unbind(),b.unbind()))
        if isinstance(a,torch.Tensor):return a.dtype==b.dtype and a.shape==b.shape and torch.equal(a.reshape(-1).view(torch.uint8),b.reshape(-1).view(torch.uint8))
        if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
        if isinstance(a,(list,tuple)):return type(a)==type(b) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
        return a==b
    with tempfile.TemporaryDirectory() as temp:
        target=Path(temp)/'types.safetensors'
        tensors={name:torch.arange(32).reshape(4,8).to(dtype) for name,dtype in fake._TYPES.items()}
        tensors['empty']=torch.empty(0,3);tensors['scalar']=torch.tensor(1.)
        save_file(tensors,str(target),metadata={'quantization':'retained'})
        loaded,metadata=fake.load_torch_file(target,return_metadata=True)
        assert equal(tensors,loaded) and metadata=={'quantization':'retained'}
        original=[(torch.arange(48,dtype=torch.float16).reshape(1,6,8),{'minimax_refs':[dict(kind='video',latent=torch.arange(24).reshape(1,2,3,4).float())],'tag':None})]
        latent={'samples':NestedTensor((torch.zeros(1,24,2,8,8),torch.zeros(1,32,2,10)))}
        manifest=packet.save_packet(original,latent,Path(temp)/'packet');a,b=packet.load_packet(manifest)
        assert equal(original,a) and equal(latent,b)
        binary=manifest.parent/'conditioning.safetensors'
        with binary.open('r+b') as f:f.seek(-1,2);x=f.read(1);f.seek(-1,2);f.write(bytes([x[0]^1]))
        try:packet.load_packet(manifest)
        except ValueError:pass
        else:raise AssertionError('Changed conditioning must be refused')
    print(json.dumps(dict(passed=True,dtypes_bit_exact=True,nested_av_exact=True,reference_latents_exact=True,tampering_refused=True)),flush=True)


if __name__=='__main__':main()
