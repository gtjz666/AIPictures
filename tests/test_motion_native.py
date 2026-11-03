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


def test_native_frame_node_keeps_rgb_and_rejects_tampering(tmp_path,monkeypatch):
    import hashlib
    import importlib.util
    from types import SimpleNamespace
    import numpy as np
    from PIL import Image
    node=Path(__file__).parents[1]/'comfy_nodes/aipictures_motion/__init__.py'
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
