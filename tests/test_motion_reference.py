import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import av
import numpy as np
import pytest
from PIL import Image

from aipictures.engine import Cancelled
from aipictures import motion_guide as motion


def gif(path):
    images=[Image.new('RGB',(64,96),c) for c in ('red','green','blue')]
    images[0].save(path,save_all=True,append_images=images[1:],duration=[100,400,700],loop=0)
    return path


def test_gif_preserves_variable_frame_delays_and_input_bytes(tmp_path):
    source=gif(tmp_path/'motion.gif');before=source.read_bytes()
    report=motion.prepare(source,tmp_path/'normalized',1.2,0.,threading.Event())
    assert report['fps']==24 and report['frames']==28 and not report['audio']
    assert report['source']['duration']==pytest.approx(1.2) and not report['temporal_blending']
    with av.open(report['path']) as c:
        pixels=[f.to_ndarray(format='rgb24')[0,0].tolist() for f in c.decode(video=0)]
        assert not c.streams.audio
    assert pixels[:3]==[[255,0,0]]*3  # 0, .0417, .0833 seconds.
    assert pixels[3:12]==[[0,128,0]]*9  # Held until the .5-second transition.
    assert pixels[12:]==[[0,0,255]]*16
    assert source.read_bytes()==before
    assert len(report['preview_frames'])==28


def test_motion_range_is_explicit_and_existing_results_not_overwritten(tmp_path):
    source=gif(tmp_path/'motion.gif')
    report=motion.prepare(source,tmp_path/'cut',1.,.1,threading.Event())
    assert report['start_seconds']==.1 and report['frames']==24
    with pytest.raises(ValueError,match='已有记录'):
        motion.prepare(source,tmp_path/'cut',1.,.1,threading.Event())
    with pytest.raises(ValueError,match='不足'):
        motion.prepare(source,tmp_path/'bad',1.,.8,threading.Event())
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):motion.prepare(source,tmp_path/'cancel',1.,0.,cancel)
    assert not (tmp_path/'cancel/guide.mp4').exists()


def test_static_image_cannot_masquerade_as_motion(tmp_path):
    path=tmp_path/'still.gif';Image.new('RGB',(64,64)).save(path)
    with pytest.raises(ValueError,match='静态图片'):motion.inspect(path)


def test_h3_alignment_holds_last_frame_and_never_drops_end_motion(tmp_path):
    source=gif(tmp_path/'motion.gif')
    r=motion.prepare(source,tmp_path/'aligned',1.2,0.,threading.Event(),max_side=512,align_h3=True)
    assert r['frames']==39 and r['last_frame_padding']==11 and r['used_seconds']==pytest.approx(28/24)
    assert (r['frames']-5)%17==0 and r['max_side']==512
    with av.open(r['path']) as c:
        data=[f.to_ndarray(format='rgb24')[0,0].tolist() for f in c.decode(video=0)]
    assert data[-12:]==[[0,0,255]]*12


def test_character_and_motion_are_independent_native_inputs(tmp_path):
    source=gif(tmp_path/'motion.gif');image=tmp_path/'character.png'
    Image.new('RGBA',(64,96),(10,100,240,255)).save(image)
    before=image.read_bytes()
    report=motion.prepare(source,tmp_path/'prepared',1.2,0.,threading.Event(),encode_video=False,save_frames=True)
    assert report['role']=='motion_only' and not report['audio']
    assert image.read_bytes()==before
    text=motion.prompt('保留蓝色衣服，完成这个动作',True)
    assert '保留蓝色衣服，完成这个动作' in text and '<Picture 1>' in text and '<Video 1>' in text
    assert 'subject_definitions:' in text and 'retention_analysis:' in text


def test_text_appearance_can_combine_with_motion_without_character_image(tmp_path):
    assert '<Picture 1>' not in motion.prompt('黄色角色',False) and '黄色角色' in motion.prompt('黄色角色',False)


def test_old_fast_engine_rejects_motion_instead_of_falling_back(tmp_path):
    from aipictures.h3_backend import generate
    with pytest.raises(ValueError,match='专用Ref2VA'):
        generate(tmp_path,dict(motion_reference='source.gif'),threading.Event(),lambda *_:None)


def test_actual_motion_ui_is_animation_only_and_freezes_both_sources():
    result=subprocess.run([sys.executable,'-m','tests.live_motion_reference'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONUTF8='1'),capture_output=True,timeout=40)
    assert result.returncode==0,result.stdout.decode('utf-8','replace')+result.stderr.decode('utf-8','replace')


def test_png_sequence_natural_order_fps_freeze_and_no_video_decoder(tmp_path,monkeypatch):
    from aipictures.frame_motion_input import import_frames,freeze
    sources=[]
    for name,color in [('frame_10.png','blue'),('frame_2.png','green'),('frame_1.png','red')]:
        p=tmp_path/name;Image.new('RGBA',(32,48),color).save(p);sources.append(p)
    owned=tmp_path/'owned';owned.mkdir()
    source,meta=import_frames(sources,12,owned,threading.Event())
    assert meta['duration']==.25
    assert [p.name for p in sources]==['frame_10.png','frame_2.png','frame_1.png']
    frozen=freeze(source,tmp_path/'job',threading.Event())
    for p in sources:p.unlink()
    monkeypatch.setattr(av,'open',lambda *_a,**_k:pytest.fail('PNG sequence must not enter a video decoder/encoder'))
    result=motion.prepare(frozen,tmp_path/'prepared',1.,0.,threading.Event(),max_side=512,
                          repeat=True,align_h3=True,encode_video=False,save_frames=True)
    assert result['frames']==39 and result['repeat'] and result['last_frame_padding']==0
    assert not list((tmp_path/'prepared').glob('*.mp4'))
    data,paths=motion.sequence(Path(result['path']))
    assert data['fps']==24
    colors=[Image.open(p).convert('RGB').getpixel((0,0)) for p in paths]
    assert colors[:6]==[(255,0,0)]*2+[(0,128,0)]*2+[(0,0,255)]*2
    assert colors[6:12]==colors[:6]


def test_png_manifest_rejects_escaped_and_changed_frames(tmp_path):
    from aipictures.frame_motion_input import import_frames
    paths=[]
    for i in range(2):
        p=tmp_path/f'{i}.png';Image.new('RGB',(32,48)).save(p);paths.append(p)
    owned=tmp_path/'owned';owned.mkdir();source,_=import_frames(paths,24,owned,threading.Event())
    data=json.loads(source.read_text('utf-8'));data['frames'][0]['image']='../0.png'
    source.write_text(json.dumps(data),'utf-8')
    with pytest.raises(ValueError,match='相对路径'):motion.inspect(source)
    data['frames'][0]['image']='frames/frame_0000.png';source.write_text(json.dumps(data),'utf-8')
    Image.new('RGB',(32,48),'white').save(owned/'frames/frame_0000.png')
    with pytest.raises(ValueError,match='修改'):motion.inspect(source)


def test_short_gif_repeats_entire_cycle_not_last_frame_only(tmp_path):
    images=[Image.new('RGB',(30,22),c) for c in ('red','blue')]
    source=tmp_path/'short.gif';images[0].save(source,save_all=True,append_images=images[1:],duration=[80,120])
    r=motion.prepare(source,tmp_path/'short',2.,0.,threading.Event(),repeat=True,align_h3=True,
                     encode_video=False,save_frames=True)
    _,paths=motion.sequence(Path(r['path']))
    colors=[Image.open(p).getpixel((0,0)) for p in paths]
    assert len(paths)==56 and colors.count((255,0,0))>15 and colors.count((0,0,255))>15
    assert r['repeat'] and r['last_frame_padding']==0


def test_native_graph_separates_dynamic_reference_slots_and_base_sampler():
    from aipictures.motion_native_graph import build,MODEL,ENCODER,VAE
    info={n:{} for n in ('MiniMaxH3ReferenceToVideo','AIPicturesMotionFrames','BasicGuider','BasicScheduler','SamplerCustomAdvanced')}
    for node,field,name in [('UNETLoader','unet_name',MODEL),('CLIPLoader','clip_name',ENCODER),('VAELoader','vae_name',VAE)]:
        info[node]={'input':{'required':{field:([name],)}}}
    g=build(info,'appearance + action',42,512,768,56,'motion/frames.json','character.png')
    refs=g['references']['inputs']
    assert refs['ref_videos.ref_video_0']==['motion',0] and refs['ref_images.ref_image_0']==['character',0]
    assert g['sample']['inputs']['latent_image']==['references',1]
    assert g['sigmas']['inputs']['steps']==20
    assert not any('Lora' in n['class_type'] or 'Guide' in n['class_type'] and n['class_type']!='BasicGuider' for n in g.values())
