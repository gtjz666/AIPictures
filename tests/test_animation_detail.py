import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image,ImageOps
import pytest

from aipictures.animation_detail import detail_settings
from aipictures.character_profile import rig_document
from aipictures.pose_animation import generate, video_workflow, export_frames
from aipictures.motion_clip import make_clip
from tests.test_generation_reference import analysis_geometry


@pytest.mark.parametrize('profile,size', [('native',(768,1024)),('preview',(480,640))])
def test_native_size_and_sampler_reach_pose_images_latent_and_manifest(tmp_path, profile, size):
    source=tmp_path/'source.png';Image.new('RGB',(768,1024),(180,90,40)).save(source)
    rig=tmp_path/'rig.json';rig.write_text(json.dumps(rig_document()),encoding='utf-8')
    analysis=dict(analysis_geometry(),rig=str(rig))
    client=Mock();client.discover.return_value={'object_info':{}}
    client.upload_image.side_effect=lambda p,**kw:Path(p).name
    latent=tmp_path/'samples.latent';latent.write_bytes(b'valid-test-data')
    client.generate.side_effect=[{'images':[],'latents':[str(latent)],'prompt_id':'sampled'},
        {'images':[str(source)]*(33 if profile=='native' else 17),'prompt_id':'owned'}]
    output=tmp_path/'animation';output.mkdir()
    with patch('aipictures.pose_animation.prepare_motion_reference',return_value=analysis), \
         patch('aipictures.pose_animation.release_idle_models',return_value={}), \
         patch('aipictures.pose_animation.bind_model_names'):
        generate(client,output,'character','',42,8,8,Mock(),threading.Event(),reference=source,
            raw_only=True,detail=profile,sampler='dpmpp_2m')
    graph=json.loads((output/'video/workflow.json').read_text('utf-8'))
    manifest=json.loads((output/'sequence.json').read_text('utf-8'))
    assert (graph['8']['inputs']['width'],graph['8']['inputs']['height'])==size
    assert graph['11']['inputs']['sampler_name']=='dpmpp_2m'
    assert manifest['spatial_detail']['inference_canvas']==list(size)
    assert manifest['spatial_detail']['post_enlargement']==(profile=='preview')
    for p in (output/'poses').glob('*.png'):
        with Image.open(p) as image:assert image.size==size


def test_default_native_graph_has_no_upscale_sharpen_or_temporal_postprocessor():
    graph=video_workflow('reference',['pose']*17,'motion','',123)
    assert graph['8']['inputs']['width']==768 and graph['8']['inputs']['height']==1024
    assert graph['13']['class_type']=='VAEDecode'
    assert graph['14']['inputs']['images']==['13',0]
    assert not any('Upscale' in n['class_type'] or 'Sharpen' in n['class_type'] for n in graph.values())
    assert detail_settings()['automatic_restoration'] is False


@pytest.mark.parametrize('size',[(767,1024),(64,128),(768,1030)])
def test_invalid_native_dimensions_are_rejected_before_submitting(size):
    with pytest.raises(ValueError,match='16 的倍数'):
        video_workflow('reference',['pose']*17,'motion','',123,size=size)


def test_unknown_profile_or_sampler_does_not_silently_fall_back():
    with pytest.raises(ValueError,match='清晰度'):detail_settings('unknown')
    with pytest.raises(ValueError,match='采样'):detail_settings(sampler='unknown')


@pytest.mark.parametrize('use_cache,direction',[(False,'right'),(True,'right'),(True,'left')])
def test_default_native_export_preserves_rgb_texture_instead_of_recoloring(tmp_path,use_cache,direction):
    image=Image.new('RGBA',(768,1024))
    image.paste((180,90,40,255),(300,30,470,970))
    for y in range(50,950,2):image.putpixel((350,y),(181,91,41,255))
    raw=tmp_path/'raw.png';image.save(raw)
    clip=make_clip(rig_document(),'a'*64)
    manifest={'frames':[],'source_frame_count':17,'frame_count':8,'fps':8,'canvas':[768,1024],'source_direction':direction}
    cached=tmp_path/'cached.png'
    expected=ImageOps.mirror(image) if direction=='left' else image
    expected.save(cached)
    with patch('aipictures.pose_animation.foreground_rgba',side_effect=lambda image,*a,**kw:image.convert('RGBA')), \
         patch('aipictures.pose_animation.release_session'), \
         patch('aipictures.pose_animation.export_sequence',return_value={}), \
         patch('aipictures.pose_animation.build_foot_review'), \
         patch('aipictures.sequence_color.apply_correction',side_effect=AssertionError('no automatic RGB rewrite')), \
         patch('aipictures.palette_consistency.apply_palette',side_effect=AssertionError('no automatic palette rewrite')):
        output=export_frames(tmp_path,{'images':[str(raw)]*17,'prompt_id':'owned'},manifest,clip,Mock(),threading.Event(),
            matte_cache=[cached]*8 if use_cache else None)
    assert manifest['color_processing']['correction_applied'] is False
    assert manifest['color_consistency']['applied'] is False
    assert all(f['post_color_rgb_preserved'] for f in manifest['frames'])
    for path in output['frames']:
        with Image.open(path) as final:assert final.convert('RGB').tobytes()==expected.convert('RGB').tobytes()


def test_stale_alpha_cache_cannot_be_applied_to_different_generated_pixels(tmp_path):
    raw=tmp_path/'raw.png';cached=tmp_path/'cache.png'
    Image.new('RGB',(768,1024),(180,90,40)).save(raw)
    Image.new('RGBA',(768,1024),(180,90,41,255)).save(cached)
    manifest={'frames':[],'source_frame_count':17,'frame_count':8,'fps':8,'canvas':[768,1024]}
    with patch('aipictures.pose_animation.release_session'),pytest.raises(ValueError,match='拒绝复用'):
        export_frames(tmp_path,{'images':[str(raw)]*17,'prompt_id':'owned'},manifest,
            make_clip(rig_document(),'a'*64),Mock(),threading.Event(),matte_cache=[cached]*8)
