"""Read-only, one-time loader allocation comparison; never loads the diffusion network."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import psutil
import torch
from safetensors import safe_open


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--backend',choices=['mmap','pread','stream'],required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();process=psutil.Process()
    def snapshot():return process.memory_info()._asdict()
    result=dict(backend=a.backend,model=str(a.model),bytes=a.model.stat().st_size,before=snapshot())
    try:
        if a.backend=='stream':
            import importlib.util
            spec=importlib.util.spec_from_file_location('stream_weights',Path(__file__).parents[1]/'comfy_nodes/aipictures_motion/stream_weights.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            context=module.StreamWeights(a.model)
        else:context=safe_open(str(a.model),framework='pt',device='cpu',backend=a.backend)
        with context as handle:
            result['opened']=snapshot();keys=handle.keys()
            name=next(k for k in keys if k.endswith('comfy_quant'))
            if a.backend=='stream':
                row=handle.header[name];begin,end=row['data_offsets'];tensor=torch.empty(end-begin,dtype=torch.uint8)
                handle.read_into(name,memoryview(tensor.numpy()),1)
            else:tensor=handle.get_tensor(name)
            result.update(key=name,sha256=hashlib.sha256(tensor.view(torch.uint8).numpy().tobytes()).hexdigest(),after_small_tensor=snapshot())
            del tensor
        gc.collect();result.update(status='completed',after=snapshot())
    except Exception as exc:result.update(status='failed',error=str(exc),after=snapshot())
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2),'utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
