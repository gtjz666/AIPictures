"""Full-motion masters and sprite assets are separate, lossless local stages."""
import json
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import Mock,patch

import numpy as np
import pytest
from PIL import Image,ImageDraw

from aipictures.engine import Cancelled
from aipictures.lora_policy import plain_workflow
from aipictures.video_generation import compose_prompt
from aipictures.video_io import encode_pngs,preview_frames,native_rgb_frames
from aipictures.video_frames import extract_video
from aipictures.reference_edit import build,MODEL
from aipictures.workflow import ImageRequest


def frames_in(folder: Path,count=9):
    paths=[]
    for i in range(count):
        image=Image.new('RGB',(64,96),(235,231,226))
        ImageDraw.Draw(image).rectangle((10+i,20,28+i,85),fill=(22,42+i,173))
        path=folder/f'frame_{i}.png';image.save(path);paths.append(path)
    return paths


def test_master_preview_and_explicit_sprite_conversion_keep_every_rgb_pixel(tmp_path):
    paths=frames_in(tmp_path);source=tmp_path/'master.mp4';cancel=threading.Event()
    encode_pngs(paths,source,24,cancel)
    decoded,fps=preview_frames(source,tmp_path/'preview',cancel,lambda *_:None)
    assert fps==24 and len(decoded)==len(paths)
    for a,b in zip(paths,decoded):
        with Image.open(a) as original,Image.open(b) as preview:
            np.testing.assert_array_equal(np.asarray(original),np.asarray(preview.convert('RGB')))
    assert not (tmp_path/'sprite_sheet.png').exists()
    with patch('aipictures.background.foreground_rgba') as matting:
        result=extract_video(source,tmp_path/'sprites',0,8,False,False,cancel,lambda *_:None)
        matting.assert_not_called()
    manifest=json.loads(Path(result['manifest']).read_text('utf-8'))
    assert manifest['fps']==24 and manifest['frame_count']==9 and manifest['all_source_frames']
    assert not manifest['temporal_blending'] and not manifest['content_scaled']
    with Image.open(tmp_path/'sprites/sprite_sheet.png') as sheet:
        for i,frame in enumerate(manifest['frames']):
            with Image.open(tmp_path/'sprites'/frame['image']) as asset,Image.open(decoded[i]) as original:
                assert asset.tobytes()==original.tobytes()
                assert sheet.crop(((i%4)*64,(i//4)*96,(i%4+1)*64,(i//4+1)*96)).tobytes()==asset.tobytes()


def test_video_encode_cancel_preserves_originals_and_does_not_publish_partial(tmp_path):
    paths=frames_in(tmp_path);before=[p.read_bytes() for p in paths]
    event=threading.Event();event.set()
    with pytest.raises(Cancelled):encode_pngs(paths,tmp_path/'master.mp4',24,event)
    assert not (tmp_path/'master.mp4').exists()
    assert [p.read_bytes() for p in paths]==before


def test_native_rgb_artifact_bypasses_lossy_video_and_keeps_exact_pixels(tmp_path):
    rng=np.random.default_rng(123);array=rng.integers(0,256,(4,32,64,3),dtype=np.uint8)
    source=tmp_path/'rgb.npy';np.save(source,array,allow_pickle=False)
    paths=native_rgb_frames(source,tmp_path/'native',threading.Event(),lambda *_:None)
    for i,path in enumerate(paths):
        with Image.open(path) as frame:np.testing.assert_array_equal(np.asarray(frame),array[i])
    invalid=tmp_path/'invalid.npy';np.save(invalid,array.astype(np.float32))
    with pytest.raises(ValueError,match='uint8 RGB'):native_rgb_frames(invalid,tmp_path/'bad',threading.Event(),lambda *_:None)


def test_bypass_chained_loras_only_in_working_copy():
    graph={'base':{'class_type':'CheckpointLoaderSimple','inputs':{}},
        'first':{'class_type':'LoraLoader','inputs':{'model':['base',0],'clip':['base',1],'lora_name':'old'}},
        'second':{'class_type':'LoraLoaderModelOnly','inputs':{'model':['first',0],'lora_name':'old2'}},
        'sample':{'class_type':'KSampler','inputs':{'model':['second',0]}},
        'text':{'class_type':'CLIPTextEncode','inputs':{'clip':['first',1]}}}
    before=json.dumps(graph)
    result=plain_workflow(graph)
    assert result['sample']['inputs']['model']==['base',0]
    assert result['text']['inputs']['clip']==['base',1]
    assert json.dumps(graph)==before and not any('Lora' in n['class_type'] for n in result.values())


def test_unknown_lora_node_rejected_without_silent_weight_changes():
    with pytest.raises(ValueError,match='特殊LoRA'):
        plain_workflow({'x':{'class_type':'CustomLoraStack','inputs':{}}})


def test_action_description_not_overridden_by_bones_or_forced_profile():
    text=compose_prompt('红色连衣裙','转向正面，随后平躺在地上',True)
    assert '转向正面，随后平躺在地上' in text
    assert '允许完成动作所需的转身' in text
    assert '侧视' not in text and '骨骼' not in text
    with pytest.raises(ValueError):compose_prompt('角色','',False)


def test_missing_wan_models_fail_before_creating_an_anchor_or_submitting_gpu_work(tmp_path):
    from aipictures.video_generation import generate
    client=Mock();client.discover.return_value={'object_info':{}}
    with pytest.raises(ValueError,match='Wan 动画工作流已停用'):
        generate(client,tmp_path/'job',{'engine':'wan'},threading.Event(),lambda *_:None)
    client.generate.assert_not_called()
    assert json.loads((tmp_path/'job/video.json').read_text('utf-8'))['status']=='failed'


def test_semantic_reference_editor_retains_chinese_and_requested_view_changes():
    request=ImageRequest(MODEL,'转向正面，双手举起','多余手指',768,1024,40,4.,123,'euler','simple')
    graph,mapping=build(request,'reference.png',{'AIPicturesReleaseCompletedEncoders':{}})
    assert '转向正面，双手举起' in graph['positive']['inputs']['prompt']
    assert '而非照抄原图' in graph['positive']['inputs']['prompt']
    assert graph['reference']['inputs']['image']=='reference.png'
    assert graph['sample']['inputs']['seed']==123
    assert graph['release']['inputs']['conditioning']==['ready',0]
    assert mapping['reference']==['reference'] and not any('lora' in v['class_type'].lower() for v in graph.values())


def test_managed_lora_deletion_keeps_changed_and_outside_files(tmp_path):
    import tools.remove_managed_loras as remover
    catalog=json.loads((Path(remover.__file__).parents[1]/'aipictures/resources/lora_catalog.json').read_text('utf-8'))
    first=catalog['models'][0];relative=first['filename'].replace('\\','/').removeprefix('AIPictures/')
    model_root=tmp_path/'models';managed=model_root/'loras/AIPictures'/relative
    managed.parent.mkdir(parents=True);managed.write_bytes(b'abc')
    outside=tmp_path/'user.safetensors';outside.write_bytes(b'original')
    receipt=tmp_path/'receipt.json'
    rows=[{'path':str(managed),'bytes':3,'sha256':first['download']['sha256']},
          {'path':str(outside),'bytes':8,'sha256':first['download']['sha256']}]
    receipt.write_text(json.dumps({'files':rows}))
    with patch.object(remover,'digest',return_value='modified'):
        result=remover.remove([receipt],model_root,tmp_path/'report.json')
    assert result['reclaimed_bytes']==0 and managed.exists() and outside.exists()
    with patch.object(remover,'digest',return_value=first['download']['sha256']):
        result=remover.remove([receipt],model_root,tmp_path/'report.json')
    assert result['reclaimed_bytes']==3 and not managed.exists() and outside.read_bytes()==b'original'


def test_h3_process_uses_actual_entrypoint_and_installed_paths_without_matting(tmp_path):
    from aipictures.h3_backend import generate
    source=tmp_path/'ref.png';Image.new('RGBA',(32,32),(40,100,180,128)).save(source)
    folder=tmp_path/'job';folder.mkdir()
    config={key:str(tmp_path/key) for key in ('cache','base','checkpoint','encoder_root','encoder','model_paths','source','root','vdn_root')}
    config.update(python=sys.executable,validated=True,width=768,height=1024)
    params={'h3_settings':config,'reference':str(source),'prompt':'保留角色','action_description':'挥手','negative':'模糊','seconds':4,'seed':123}
    commands=[]
    def process(command,**kwargs):
        commands.append(command);(folder/'animation.mp4').write_bytes(b'stub-output')
        return Mock(pid=123,poll=Mock(return_value=0),returncode=0)
    with patch('aipictures.h3_backend.subprocess.Popen',side_effect=process),\
         patch('aipictures.engine.ComfyClient') as client,patch('aipictures.engine_service.release_idle_models'),\
         patch('aipictures.background.foreground_rgba') as matte:
        client.return_value.request.return_value={'queue_running':[],'queue_pending':[]}
        result=generate(folder,params,threading.Event(),lambda *_:None)
        matte.assert_not_called()
    cmd=json.loads((folder/'h3-command.json').read_text('utf-8'))['command']
    assert cmd[cmd.index('-m')+1]=='freevideo_engine'
    assert 'runpy.run_module' in commands[0][commands[0].index('-c')+1]
    for field in ('checkpoint','model_paths','encoder_root'):
        assert cmd[cmd.index('--'+field.replace('_','-'))+1]==config[field]
    assert '--task' in cmd and result['style_lora'] is False
    assert Image.open(folder/'reference_rgb.png').mode=='RGB'
    assert Image.open(source).getpixel((0,0))==(40,100,180,128)


def test_live_full_animation_ui():
    import os
    result=subprocess.run([sys.executable,'-m','tests.live_video_first'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=40)
    assert result.returncode==0,result.stdout.decode('utf-8','replace')+result.stderr.decode('utf-8','replace')


def test_cancels_only_own_isolated_real_child_and_records_exit(tmp_path):
    from aipictures.h3_backend import generate
    source=tmp_path/'source';package=source/'freevideo_engine';package.mkdir(parents=True)
    (package/'__init__.py').write_text('')
    (package/'__main__.py').write_text('import time\nprint(\'started\',flush=True)\ntime.sleep(30)\n')
    folder=tmp_path/'job';folder.mkdir()
    config={k:str(tmp_path/k) for k in ('cache','base','checkpoint','encoder_root','encoder','model_paths','root','vdn_root')}
    config.update(python=sys.executable,source=str(source),validated=True)
    params={'h3_settings':config,'prompt':'角色','action_description':'行走','negative':'','seconds':4,'seed':123}
    cancel=threading.Event();children=[];popen=subprocess.Popen
    def start(*args,**kwargs):
        child=popen(*args,**kwargs);children.append(child);return child
    def event(kind,data):
        if kind=='h3_process':cancel.set()
    with patch('aipictures.h3_backend.subprocess.Popen',side_effect=start),\
         patch('aipictures.engine.ComfyClient') as client,patch('aipictures.engine_service.release_idle_models'):
        client.return_value.request.return_value={'queue_running':[],'queue_pending':[]}
        with pytest.raises(Cancelled):generate(folder,params,cancel,event)
    assert children[0].poll() is not None
    record=json.loads((folder/'h3-process.json').read_text('utf-8'))
    assert record['status']=='stopped' and record['pid']==children[0].pid


def test_h3_not_enabled_by_install_probes_or_unfinished_results(tmp_path):
    from tools.register_h3 import register
    root=tmp_path/'h3';root.mkdir();(root/'machine.json').write_text('{"ready":false}')
    with pytest.raises(ValueError,match='尚未完成安装'):register(root,tmp_path/'video.json',tmp_path/'data')


@pytest.mark.skipif(sys.platform!='win32',reason='Windows job-object lifecycle')
def test_owner_process_exit_kills_isolated_child_without_worker_cleanup(tmp_path):
    import ctypes as c
    from ctypes import wintypes as w
    record=tmp_path/'pid.json'
    code='\n'.join([
        'import subprocess,sys,os,time,json',
        'from pathlib import Path',
        'from aipictures.owned_process import OwnedProcessJob',
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)",
        'owner=OwnedProcessJob(child.pid)',
        f'Path({str(record)!r}).write_text(json.dumps(dict(pid=child.pid)))',
        'os._exit(0)',
    ])
    result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).parents[1],capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr.decode('utf-8','replace')
    pid=json.loads(record.read_text())['pid']
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];kernel.WaitForSingleObject.restype=w.DWORD
    kernel.CloseHandle.argtypes=[w.HANDLE]
    process=kernel.OpenProcess(0x00100000,False,pid)
    if process:
        try:assert kernel.WaitForSingleObject(process,3000)==0
        finally:kernel.CloseHandle(process)


def test_child_waits_for_ownership_gate_and_exits_if_parent_closes_pipe(tmp_path):
    from aipictures.owned_process import gated_module_command
    package=tmp_path/'fake_video';package.mkdir();(package/'__init__.py').write_text('')
    marker=tmp_path/'started.txt'
    (package/'__main__.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("started")\n')
    command=gated_module_command([sys.executable,'-u','-m','fake_video'])
    child=subprocess.Popen(command,cwd=tmp_path,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    child.stdin.close();assert child.wait(timeout=5)==125 and not marker.exists()
    child=subprocess.Popen(command,cwd=tmp_path,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    child.communicate(b'go\n',timeout=5)
    assert child.returncode==0 and marker.read_text()=='started'
