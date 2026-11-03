import json
import os
import sys
import threading
import time
from pathlib import Path
import pytest
from aipictures.motion_native_backend import NativeSession
from aipictures.engine import Cancelled


def test_output_duration_is_independent_of_short_reference():
    from aipictures.motion_native_backend import output_frames
    # A 0.87s reference without repeat must not silently shorten a requested 2s output.
    assert output_frames(2.)==56 and output_frames(2.334)==73 and output_frames(8.)==192
    with pytest.raises(ValueError):output_frames(float('nan'))


def test_cancel_terminates_only_owned_native_session(tmp_path):
    """Real HTTP startup + private process, without Torch or GPU fixtures."""
    source=tmp_path/'server';source.mkdir();folder=tmp_path/'job';folder.mkdir()
    (source/'main.py').write_text('''import sys,json
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  body=b'{"test_node":{}}';self.send_response(200);self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
HTTPServer(('127.0.0.1',int(sys.argv[sys.argv.index('--port')+1])),Handler).serve_forever()
''','utf-8')
    cancel=threading.Event();events=[]
    config=dict(python=sys.executable,source=str(source),model_paths=str(tmp_path/'paths.yaml'))
    with NativeSession(config,folder,cancel,lambda kind,data:events.append(kind)) as session:
        assert 'test_node' in session.info and session.process.poll() is None
        cancel.set();deadline=time.monotonic()+5
        while session.process.poll() is None and time.monotonic()<deadline:time.sleep(.02)
        assert session.process.poll() is not None
        with pytest.raises(Cancelled):session.check()
    assert 'h3_process' in events
    assert json.loads((folder/'native-process.json').read_text())['status']=='stopped'
    command=json.loads((folder/'native-command.json').read_text())
    assert command['environment']=={'AIPICTURES_STREAM_WEIGHTS':'1'}
    assert command['command'][command['command'].index('--reserve-vram')+1]=='3.0'
    if os.name=='nt':assert '--disable-async-offload' in command['command'] and '--disable-pinned-memory' in command['command']


def test_native_frame_node_keeps_rgb_and_rejects_tampering(tmp_path,monkeypatch):
    import hashlib
    import importlib.util
    from types import SimpleNamespace
    import numpy as np
    from PIL import Image
    node=Path(__file__).parents[1]/'comfy_nodes/aipictures_motion/frames.py'
    monkeypatch.setitem(sys.modules,'folder_paths',SimpleNamespace(get_input_directory=lambda:str(tmp_path)))
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(from_numpy=lambda x:x))
    spec=importlib.util.spec_from_file_location('test_native_frame_input',node)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    frame=tmp_path/'frame.png';Image.new('RGB',(16,24),(15,120,230)).save(frame)
    row=dict(image='frame.png',sha256=hashlib.sha256(frame.read_bytes()).hexdigest())
    manifest=tmp_path/'frames.json';manifest.write_text(json.dumps(dict(kind='motion_frames',fps=24,frames=[row]*5)))
    batch=module.AIPicturesMotionFrames().load('frames.json')[0]
    assert batch.shape==(5,24,16,3) and np.allclose(batch[0,0,0]*255,[15,120,230])
    Image.new('RGB',(16,24),'black').save(frame)
    with pytest.raises(ValueError,match='不一致'):module.AIPicturesMotionFrames().load('frames.json')


@pytest.mark.parametrize('cancel_after_encoding',[False,True])
def test_encoding_process_exits_before_sampling_and_cancel_boundary(tmp_path,monkeypatch,cancel_after_encoding):
    from PIL import Image
    from aipictures import motion_native_backend as backend,motion_native_graph as graph,motion_guide
    cancel=threading.Event();sessions=[]
    class Session:
        def __init__(self,config,folder,cancel,emit):
            self.folder=folder;self.input=folder/'native_input';self.output_dir=folder/'native_output';self.info={};self.closed=False;self.client=self
        def __enter__(self):
            if sessions:assert sessions[-1].closed
            sessions.append(self);self.input.mkdir(parents=True);self.output_dir.mkdir();return self
        def __exit__(self,*args):self.closed=True
        def check(self):pass
        def generate(self,graph,folder,emit,cancel,**kw):
            folder.mkdir(parents=True)
            if self.folder.name=='native_encode':
                assert kw['allow_latent_only']
                packet=self.output_dir/'conditioning';packet.mkdir()
                (packet/'conditioning.json').write_text('{}');(packet/'conditioning.safetensors').write_bytes(b'exact conditioning')
                return {}
            assert (self.input/'conditioning/conditioning.safetensors').read_bytes()==b'exact conditioning'
            paths=[]
            for i in range(56):
                p=folder/f'{i}.png';Image.new('RGB',(16,16),(12,34,56)).save(p);paths.append(str(p))
            return dict(images=paths)
    monkeypatch.setattr(backend,'NativeSession',Session);monkeypatch.setattr(backend,'release_shared',lambda _:None)
    monkeypatch.setattr(graph,'encoding',lambda *a:{})
    monkeypatch.setattr(graph,'sampling',lambda *a:{})
    monkeypatch.setattr(motion_guide,'prepare',lambda *a,**k:dict(source={'sha256':'ok'},frames=56))
    params=dict(seconds=2.,seed=12,prompt='Keep exact appearance',motion_reference='test.gif',motion_native_settings={'validated':True})
    def emit(kind,data):
        if cancel_after_encoding and '参考编码已保存' in data.get('message',''):cancel.set()
    if cancel_after_encoding:
        with pytest.raises(Cancelled):backend.generate(tmp_path,params,cancel,emit)
        assert len(sessions)==1 and sessions[0].closed
    else:
        result=backend.generate(tmp_path,params,cancel,emit)
        assert len(sessions)==2 and all(s.closed for s in sessions)
        assert len(result['native_frames'])==56 and result['staged'] and result['weights_loader']=='stream'
