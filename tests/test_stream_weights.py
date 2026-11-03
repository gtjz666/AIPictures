import importlib.util
import json
import struct
from pathlib import Path
import pytest


def reader():
    path=Path(__file__).parents[1]/'comfy_nodes/aipictures_motion/stream_weights.py'
    spec=importlib.util.spec_from_file_location('stream_weights_unit',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.StreamWeights


def make_file(path,header,payload):
    data=json.dumps(header).encode();path.write_bytes(struct.pack('<Q',len(data))+data+payload)


def test_stream_bytes_scalar_empty_and_metadata(tmp_path):
    path=tmp_path/'small.safetensors'
    make_file(path,{'a':dict(dtype='U8',shape=[4],data_offsets=[0,4]),
                    'b':dict(dtype='U8',shape=[],data_offsets=[4,5]),
                    'c':dict(dtype='U8',shape=[0],data_offsets=[5,5]),'__metadata__':{'test':'exact'}},b'\x00\xff\x81\x42\x09')
    with reader()(path) as r:
        assert r.keys()==['a','b','c'] and r.metadata()=={'test':'exact'}
        out=bytearray(4);r.read_into('a',memoryview(out),1);assert out==b'\x00\xff\x81\x42'
        out=bytearray(1);r.read_into('b',memoryview(out),1);assert out==b'\x09'
        r.read_into('c',memoryview(bytearray()),1)
        with pytest.raises(ValueError,match='不匹配'):r.read_into('a',memoryview(bytearray(4)),2)


@pytest.mark.parametrize('offset,shape', [([0,8],[8]),([-1,1],[2]),([1,4],[3])])
def test_invalid_ranges_refused_before_allocation(tmp_path,offset,shape):
    path=tmp_path/'bad.safetensors';make_file(path,{'x':dict(dtype='U8',shape=shape,data_offsets=offset)},b'abcd')
    with pytest.raises(ValueError):reader()(path)


def test_staged_graph_does_not_load_qwen_and_dit_together():
    from aipictures.motion_native_graph import encoding,sampling,MODEL,ENCODER,VAE
    info={n:{} for n in ('MiniMaxH3ReferenceToVideo','AIPicturesMotionFrames','BasicGuider','BasicScheduler','SamplerCustomAdvanced',
                        'AIPicturesSaveConditioning','AIPicturesLoadConditioning')}
    for node,field,name in [('UNETLoader','unet_name',MODEL),('CLIPLoader','clip_name',ENCODER),('VAELoader','vae_name',VAE)]:
        info[node]={'input':{'required':{field:([name],)}}}
    enc=encoding(info,'exact prompt',123,512,768,107,'motion/frames.json','character.png')
    sample=sampling(info,123,512,768,107)
    assert all(row['class_type']!='UNETLoader' for row in enc.values())
    assert all(row['class_type'] not in ('CLIPLoader','MiniMaxH3ReferenceToVideo','AIPicturesMotionFrames') for row in sample.values())
    assert sample['noise']['inputs']['noise_seed']==123 and sample['sigmas']['inputs']['steps']==20
