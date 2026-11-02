import importlib.util
import json
import sys
import threading
from pathlib import Path
from types import ModuleType,SimpleNamespace
from unittest.mock import Mock,patch

import av
import numpy as np
import pytest
from PIL import Image,ImageDraw

from aipictures.action_intent import appearance_description,has_pose_conflict
from aipictures.image_constraints import compile_constraints,apply_constraints
from aipictures.local_translation import translate
from aipictures.loop_frames import cycle_indices
from aipictures.keyframe_capture import keyframe_indices
from aipictures.video_frames import extract_video
from aipictures.walk_cycle import export_sequence
from aipictures import zimage
from aipictures.workflow import ImageRequest


def test_explicit_hands_constraints_do_not_select_style_or_force_other_poses():
    c=compile_constraints('单个人物，双手放在身体两侧，蓝色外套')
    p,n=apply_constraints('one person','',c)
    assert 'outside pockets' in p and 'hands in pockets' in n
    assert c['model_or_lora_selection'] is False
    assert not compile_constraints('不要双手自然下垂，举起右手')['positive']
    assert not compile_constraints('双手自然下垂，双手插兜')['positive']
    assert not compile_constraints('森林中的木屋，俯视图')['positive']


def test_one_subject_constraints_preserve_requested_sheets():
    assert 'sprite sheet' in compile_constraints('one object on gray background')['negative']
    assert not compile_constraints('one object, multiple views on a sprite sheet')['negative']


def test_preset_filters_whole_lying_clauses_but_keeps_appearance():
    text='紫色短发，白色衬衫，角色平躺在地上呈大字，背部贴地，脸朝上，双臂向身体两侧展开，双腿向两侧分开'
    assert has_pose_conflict(text,'run')
    result=appearance_description(text)
    assert '紫色短发' in result and '白色衬衫' in result
    for clause in ('平躺','贴地','朝上','展开','分开'):assert clause not in result
    assert not has_pose_conflict(text,'custom')


def test_known_art_terms_and_english_never_go_through_prose_mt():
    cancel=threading.Event()
    with patch('aipictures.local_translation.subprocess.Popen') as child:
        original='anime girl, full body, front view'
        result=translate(original,'blurry',{},cancel)
        assert result['positive']==original and not result['translated']
        translated=translate('动漫女孩，正面，全身，双手放在身体两侧','五官模糊，水印',{},cancel)
        assert 'anime girl' in translated['positive']
        assert 'facial features' in translated['negative']
        assert 'five officials' not in translated['negative']
        child.assert_not_called()


def test_cycles_pick_only_real_frames_without_modifying_assets(tmp_path):
    paths=[]
    for i in range(33):
        image=Image.new('RGBA',(64,96));draw=ImageDraw.Draw(image)
        x=25+round(8*np.sin(i*np.pi/8))
        draw.rectangle((x,15,x+12,85),fill=(60,95,180,255))
        path=tmp_path/f'frame_{i:03d}.png';image.save(path);paths.append(path)
    before=[p.read_bytes() for p in paths]
    indices,report=cycle_indices(paths,8)
    assert len(indices)==8 and len(set(indices))==8
    assert max(indices)<report['endpoint']
    assert report['endpoint_duplicate_excluded'] and report['guaranteed_seamless'] is False
    assert before==[p.read_bytes() for p in paths]
    exports=export_sequence(tmp_path,[paths[i] for i in indices],8,'custom',loop=True)
    assert exports['cell_size']==[64,96] and exports['loop'] and exports['gif_size']==[64,96]
    with Image.open(tmp_path/'sprite_sheet.png') as sheet:
        for i,index in enumerate(indices):
            assert sheet.crop(((i%4)*64,(i//4)*96,(i%4+1)*64,(i//4+1)*96)).tobytes()==Image.open(paths[index]).tobytes()


def test_static_clip_warns_instead_of_claiming_motion(tmp_path):
    paths=[]
    for i in range(17):
        p=tmp_path/f'{i}.png';Image.new('RGBA',(32,48),(55,65,75,255)).save(p);paths.append(p)
    _,report=cycle_indices(paths,8)
    assert report['warnings'] and not report['guaranteed_seamless']


def test_keyframe_capture_keeps_brief_extreme_and_real_transition_frames(tmp_path):
    paths=[]
    for i in range(33):
        image=Image.new('RGBA',(64,96))
        x=42 if i==3 else 10
        ImageDraw.Draw(image).rectangle((x,15,x+12,85),fill=(40,90,150,255))
        path=tmp_path/f'frame_{i}.png';image.save(path);paths.append(path)
    before=[p.read_bytes() for p in paths]
    indices,report=keyframe_indices(paths,8)
    assert len(indices)==len(set(indices))==8 and indices==sorted(indices)
    assert 3 in report['key_source_indices'] and 3 in indices
    assert indices[0]==0 and indices[-1]==32
    assert not report['synthesized_frames']
    assert before==[p.read_bytes() for p in paths]
    with pytest.raises(ValueError,match='严格递增'):
        keyframe_indices(paths,8,[0.]*33)


def test_direct_gif_import_with_eight_frames_supports_keyframe_loop(tmp_path):
    frames=[]
    for i in range(8):
        image=Image.new('RGB',(64,96),(235,235,235))
        ImageDraw.Draw(image).rectangle((10+i*3,15,25+i*3,85),fill=(40,90,150))
        frames.append(image)
    source=tmp_path/'motion.gif'
    frames[0].save(source,save_all=True,append_images=frames[1:],duration=125,loop=0)
    result=extract_video(source,tmp_path/'out',8,8,True,False,threading.Event(),lambda *_:None,sampling='keyframes')
    report=json.loads(Path(result['manifest']).read_text('utf-8'))
    assert report['status']=='completed' and len(report['frames'])==8
    assert report['pose_selection']['keyframe_capture']['synthesized_frames'] is False
    for frame in report['frames']:
        with Image.open(tmp_path/'out'/frame['image']) as asset,Image.open(
            tmp_path/'out/source_frames'/f'source_{frame["source_frame"]:04d}.png') as raw:
            assert asset.tobytes()==raw.tobytes()


def test_real_lossless_video_decode_and_sprite_readback(tmp_path):
    source=tmp_path/'test.mkv'
    with av.open(str(source),'w') as container:
        stream=container.add_stream('ffv1',rate=24);stream.width=64;stream.height=96;stream.pix_fmt='bgra'
        for i in range(49):
            image=Image.new('RGB',(64,96),(230,230,230));draw=ImageDraw.Draw(image)
            x=25+round(7*np.sin(i*np.pi/12));draw.rectangle((x,10,x+12,87),fill=(50,85,160))
            for packet in stream.encode(av.VideoFrame.from_image(image)):container.mux(packet)
        for packet in stream.encode():container.mux(packet)
    before=source.read_bytes();out=tmp_path/'out'
    result=extract_video(source,out,8,8,True,False,threading.Event(),lambda *_:None)
    manifest=json.loads(Path(result['manifest']).read_text('utf-8'))
    assert manifest['status']=='completed' and manifest['loop'] and manifest['canvas']==[64,96]
    assert manifest['content_scaled'] is False and manifest['temporal_blending'] is False
    for frame in manifest['frames']:
        raw=out/'source_frames'/f'source_{frame["source_frame"]:04d}.png'
        with Image.open(raw) as original,Image.open(out/frame['image']) as asset:
            assert original.tobytes()==asset.tobytes()
    assert source.read_bytes()==before
    with pytest.raises(ValueError,match='已有任务'):
        extract_video(source,out,8,8,True,False,threading.Event(),lambda *_:None)


def test_transparent_video_keeps_existing_alpha_without_segmenting_again(tmp_path):
    source=tmp_path/'transparent.mkv'
    with av.open(str(source),'w') as container:
        stream=container.add_stream('ffv1',rate=24)
        stream.width=64;stream.height=96;stream.pix_fmt='bgra'
        for i in range(49):
            image=Image.new('RGBA',(64,96),(160,30,40,0))
            ImageDraw.Draw(image).rectangle((20,10,40,85),fill=(40,90+i,150,255))
            for packet in stream.encode(av.VideoFrame.from_ndarray(np.asarray(image),format='rgba')):container.mux(packet)
        for packet in stream.encode():container.mux(packet)
    with patch('aipictures.background.session',side_effect=AssertionError('Existing matte must be preserved')):
        result=extract_video(source,tmp_path/'out',8,8,False,True,threading.Event(),lambda *_:None)
    manifest=json.loads(Path(result['manifest']).read_text('utf-8'))
    assert manifest['post_color_rgb_preserved']
    for frame in manifest['frames']:
        with Image.open(tmp_path/'out'/frame['image']) as asset:
            assert asset.getpixel((0,0))==(160,30,40,0)
            assert asset.getpixel((30,30))[3]==255


def test_runtime_wrapper_releases_encoders_before_official_encode_and_keeps_values():
    calls=[]
    class VAE:
        def encode(self,pixels):calls.append('encode');return pixels
    class Original:
        @classmethod
        def define_schema(cls):return SimpleNamespace(node_id='WanAnimateToVideo')
        @classmethod
        def execute(cls,**kwargs):
            assert kwargs['width']==768 and kwargs['height']==1024
            for frames in (1,33,33):kwargs['vae'].encode(np.zeros((frames,1)))
            return kwargs['positive'],kwargs['negative'],kwargs['length']
    memory=ModuleType('comfy.model_management')
    memory.unload_all_models=lambda:calls.append('unload')
    memory.soft_empty_cache=lambda:calls.append('release')
    server=SimpleNamespace(last_node_id='8',client_id='owned',send_sync=Mock())
    modules={'comfy':ModuleType('comfy'),'comfy.model_management':memory,
        'comfy_api':ModuleType('comfy_api'),'comfy_api.latest':SimpleNamespace(ComfyExtension=object,io=SimpleNamespace(ComfyNode=object)),
        'comfy_extras':ModuleType('comfy_extras'),'comfy_extras.nodes_wan':SimpleNamespace(WanAnimateToVideo=Original,WanImageToVideo=Original),
        'server':SimpleNamespace(PromptServer=SimpleNamespace(instance=server))}
    path=Path(__file__).resolve().parents[1]/'comfy_nodes/aipictures_runtime/__init__.py'
    spec=importlib.util.spec_from_file_location('test_runtime_wrapper',path);module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,modules):spec.loader.exec_module(module)
    result=module.AIPicturesWanAnimateToVideo.execute(vae=VAE(),width=768,height=1024,length=33,
        positive='unchanged positive',negative='unchanged negative')
    assert result==('unchanged positive','unchanged negative',33)
    assert calls==['unload','release','encode','encode','encode']
    assert server.send_sync.call_count==5


def test_native_chinese_graph_uses_own_encoder_and_cfg1_constraints():
    info={node:{'input':{'required':{field:[[name]]}}} for node,field,name in
        (('UNETLoader','unet_name',zimage.UNET),('CLIPLoader','clip_name',zimage.ENCODER),('VAELoader','vae_name',zimage.VAE))}
    info.update(EmptySD3LatentImage={},ModelSamplingAuraFlow={},ConditioningZeroOut={})
    assert zimage.available(info)
    graph,mapping=zimage.build(ImageRequest('unused','动漫人物，双手下垂','水印',1024,1024),info)
    assert '动漫人物' in graph['text']['inputs']['text'] and '水印' in graph['text']['inputs']['text']
    assert graph['clip']['inputs']['type']=='lumina2' and graph['sample']['inputs']['steps']==9
    assert graph['negative']['class_type']=='ConditioningZeroOut' and mapping['negative']==[]
    with pytest.raises(ValueError,match='不使用.*LoRA'):
        zimage.build(ImageRequest('unused','人物',lora='manual.safetensors'),info)
