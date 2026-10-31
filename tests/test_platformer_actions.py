import json
import math
import threading
from pathlib import Path
from unittest.mock import Mock,patch

import pytest
from PIL import Image
from aipictures.character_profile import rig_document
from aipictures.motion_clip import make_clip,sample_clip
from aipictures.motion_language import make_custom_clip,parse_plan,rebuild_clip
from aipictures.game_animation import export_game_data,preview_offset
from aipictures.gif_export import save_gif
from aipictures.animation_style import style_workflow
from aipictures.custom_animation import custom_prompt,generate


def test_platformer_jump_has_fixed_root_and_asymmetric_airborne_pose():
    clip=make_clip(rig_document(),'a'*64,'jump',16);base=clip['base_rig']['joints']
    for phase in (.25,.4,.5,.6,.7):
        pose=sample_clip(clip,phase);p=pose['joints']
        assert p['right_hip'][1]==pytest.approx(base['right_hip'][1])
        assert not any(pose['contacts'].values())
        assert abs(p['right_wrist'][1]-p['left_wrist'][1])>40
        assert abs(p['right_knee'][0]-p['left_knee'][0])>40
    assert sample_clip(clip,0)['joints']==sample_clip(clip,1)['joints']
    legacy=dict(clip,generator_version=3)
    assert sample_clip(legacy,.5)['joints']['right_hip'][1]<base['right_hip'][1]-30


def test_attack_contacts_extension_and_recovery():
    clip=make_clip(rig_document(),'b'*64,'attack');rest=sample_clip(clip,0)['joints']
    hit=sample_clip(clip,.4)
    assert hit['hitbox_active'] and all(hit['contacts'].values())
    assert hit['joints']['right_wrist'][0]>rest['right_wrist'][0]+180
    assert abs(hit['joints']['right_wrist'][0]-hit['joints']['left_wrist'][0])>60
    assert sample_clip(clip,1)['joints']==rest


def test_custom_plan_order_proportions_and_unknown_rejection():
    plan=parse_plan('先下蹲1秒，然后向前出拳2秒，最后待机1秒')
    assert [s['action'] for s in plan['segments']]==['squat','attack','idle']
    assert plan['duration_seconds']==4
    assert [s['action'] for s in parse_plan('横版跳跃，然后基础攻击')['segments']]==['jump','attack']
    clip=make_custom_clip(rig_document(),'a'*64,plan['description'])
    assert sample_clip(clip,.125)['segment']==0
    assert sample_clip(clip,.5)['segment']==1
    assert sample_clip(clip,.9)['segment']==2
    assert rebuild_clip(clip)['motion_plan']==plan
    assert sample_clip(clip,0)['joints']==sample_clip(clip,1)['joints']
    for text in ('挥手告别','不要攻击','下蹲然后后空翻','跑步100秒','出拳两次','缓慢走路','走路并攻击'):
        with pytest.raises(ValueError):parse_plan(text)


def test_custom_transitions_preserve_limbs_and_plan_survives_edits():
    clip=make_custom_clip(rig_document(),'a'*64,'走路，然后跳跃，然后出拳',16)
    base=clip['base_rig']['joints']
    for phase in [i/128 for i in range(129)]:
        p=sample_clip(clip,phase)['joints']
        for side in ('right','left'):
            for a,b in (('hip','knee'),('knee','ankle'),('shoulder','elbow'),('elbow','wrist')):
                a,b=side+'_'+a,side+'_'+b
                assert math.dist(p[a][:2],p[b][:2])==pytest.approx(math.dist(base[a][:2],base[b][:2]),abs=1e-5)
    clip['edited']=True;clip['frames'][3]['joints']['right_wrist'][0]+=10
    assert sample_clip(clip,3/15)['joints']==clip['frames'][3]['joints']


def test_game_metadata_and_preview_do_not_modify_png(tmp_path):
    frames=[];hashes=[]
    for i in range(8):
        path=tmp_path/f'frame_{i:03d}.png'
        Image.new('RGBA',(768,1024),(i*20,60,120,255)).save(path)
        hashes.append(path.read_bytes());frames.append({'image':path.name,'phase':i/7})
    manifest={'action':'jump','frames':frames,'fps':8,'exports':{}}
    export_game_data(tmp_path,manifest)
    assert manifest['game_animation']['root_motion_baked'] is False
    assert set(sum(manifest['game_animation']['clips'].values(),[]))==set(range(8))
    assert preview_offset(0)==preview_offset(1)==0 and preview_offset(.47)==-160
    assert hashes==[(tmp_path/f['image']).read_bytes() for f in frames]
    with Image.open(tmp_path/'jump_game_preview.gif') as gif:
        assert gif.size==(384,608) and gif.n_frames==8 and gif.info['loop']==0
    manifest['action']='attack';export_game_data(tmp_path,manifest)
    assert manifest['game_animation']['clips']['active']==[3]


def test_gif_timing_preserves_eight_fps(tmp_path):
    images=[Image.new('RGBA',(10,10),(i*20,50,100,255)) for i in range(8)]
    save_gif(images,tmp_path/'single.gif',8,loop=False,size=(10,10))
    with Image.open(tmp_path/'single.gif') as gif:
        durations=[]
        for i in range(gif.n_frames):gif.seek(i);durations.append(gif.info['duration'])
        assert sum(durations)==1000 and 'loop' not in gif.info


def test_style_lora_connected_to_sdxl_anchor_not_wan():
    graph=style_workflow('ref.png','sd_xl_base_1.0_0.9vae.safetensors','manual-style.safetensors',.8,42)
    assert graph['8']['class_type']=='LoraLoader'
    assert graph['reference_condition']['inputs']['model']==['8',0]
    assert graph['5']['inputs']['latent_image']==['style_encode',0]
    assert graph['5']['inputs']['denoise']==.62
    assert graph['style_encode']['inputs']['pixels']==['style_scale',0]
    assert not any('Wan' in n['class_type'] for n in graph.values())
    with pytest.raises(ValueError):style_workflow('ref.png','sdxl','',.8,42)


def test_free_custom_preserves_arbitrary_description_and_entire_clip(tmp_path):
    description='挥手告别，然后转身坐下'
    assert description in custom_prompt(description)
    assert '左右腿交替' not in custom_prompt(description)
    assert '不要用静止站立或走路' not in custom_prompt('走路')
    source=tmp_path/'reference.png';Image.new('RGBA',(768,1024),(120,80,60,255)).save(source)
    latent=tmp_path/'sample.latent';latent.write_bytes(b'latent')
    client=Mock();client.url='http://127.0.0.1:8188';client.discover.return_value={'object_info':{}}
    client.upload_image.side_effect=lambda p,**_:Path(p).name
    client.generate.side_effect=[{'latents':[str(latent)],'images':[],'prompt_id':'owned-sample'},
        {'images':[str(source)]*33,'prompt_id':'owned-decode'}]
    with patch('aipictures.custom_animation.check_video_models'),patch('aipictures.custom_animation.release_idle_models'),\
        patch('aipictures.animation_decode.release_idle_models',return_value={}),\
        patch('aipictures.custom_animation.foreground_rgba',side_effect=lambda im,*_,**__:im.convert('RGBA')):
        result=generate(client,tmp_path/'out','','',42,8,8,Mock(),threading.Event(),source,custom_description=description)
    graph=client.generate.call_args_list[0].args[0]
    assert description in graph['5']['inputs']['text']
    assert graph['8']['class_type']=='WanImageToVideo'
    assert graph['8']['inputs']['width']==768 and graph['8']['inputs']['height']==1024
    assert graph['11']['inputs']['cfg']==3.5
    manifest=json.loads(Path(result['manifest']).read_text('utf-8'))
    assert manifest['pose_selection']['source_indices']==[0,5,9,14,18,23,27,32]
    assert manifest['loop'] is False and all(f['post_color_rgb_preserved'] for f in manifest['frames'])


@pytest.mark.parametrize('styled',[False,True])
def test_native_compiled_action_uses_full_pose_plan_and_opt_in_anchor(tmp_path,styled):
    from aipictures.pose_animation import generate as generate_pose
    from tests.test_generation_reference import analysis_geometry
    source=tmp_path/'reference.png';Image.new('RGB',(768,1024),(130,80,60)).save(source)
    styled_source=tmp_path/'styled.png';Image.new('RGB',(768,1024),(80,100,130)).save(styled_source)
    rig=tmp_path/'rig.json';rig.write_text(json.dumps(rig_document()))
    latent=tmp_path/'sample.latent';latent.write_bytes(b'latent')
    client=Mock();client.url='http://127.0.0.1:8188';client.discover.return_value={'object_info':{}}
    client.upload_image.side_effect=lambda p,**_:Path(p).name
    client.generate.side_effect=[{'images':[],'latents':[str(latent)],'prompt_id':'sample'},
        {'images':[str(source)]*33,'prompt_id':'decode'}]
    with patch('aipictures.pose_animation.prepare_motion_reference',return_value=dict(analysis_geometry(),rig=str(rig))) as analyze,\
        patch('aipictures.pose_animation.release_idle_models',return_value={}),\
        patch('aipictures.animation_decode.release_idle_models',return_value={}),\
        patch('aipictures.pose_animation.bind_model_names'),\
        patch('aipictures.animation_style.restyle_reference',return_value=(str(styled_source),{'enabled':True})) as style:
        folder=tmp_path/'out';folder.mkdir()
        generate_pose(client,folder,'保持角色','','42',8,8,Mock(),threading.Event(),source,
            action='custom',custom_description='下蹲，然后出拳',style_reference=styled,lora='manual.safetensors',raw_only=True)
    assert style.call_count==int(styled)
    assert str(analyze.call_args.args[0])==str(styled_source if styled else source)
    graph=client.generate.call_args_list[0].args[0]
    assert '下蹲，然后出拳' in graph['5']['inputs']['text']
    assert 'LoraLoader' not in {n['class_type'] for n in graph.values()}
    poses=[json.loads(p.read_text('utf-8')) for p in sorted((folder/'poses').glob('pose_*.json'))]
    assert len(poses)==33 and poses[8]['segment']==0 and poses[24]['segment']==1
    assert len({tuple(p['joints']['right_wrist'][:2]) for p in poses})>20
