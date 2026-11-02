"""Automatic route isolation, independent references and bounded retirement."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import os
import subprocess
import sys
import threading
from dataclasses import asdict

import pytest

from aipictures import flux_klein
from aipictures.image_family import effective_family
from aipictures.workflow import ImageRequest
from tests.test_image_choice_retirement import model_info
from tools import retire_sdxl


def test_explicit_auto_routes_change_only_with_reference_presence():
    w = SimpleNamespace(model_family=Mock(), reference_path=None)
    w.model_family.currentData.return_value = 'auto'
    assert effective_family(w) == 'zimage'
    w.reference_path = Path('reference.png')
    assert effective_family(w) == 'flux_klein'
    assert effective_family(w, False) == 'zimage'
    w.model_family.currentData.return_value = 'zimage'
    assert effective_family(w) == 'zimage'  # Never replace a manually selected engine.


def test_plain_reference_preparation_needs_no_pose_or_scipy_import():
    code = '''from PIL import Image
from aipictures.reference_input import opaque_reference
import sys
im=Image.new('RGBA',(32,64),(255,0,0,0))
out=opaque_reference(im)
assert out.size==(32,64) and out.getpixel((0,0))==(242,243,245)
assert 'scipy' not in sys.modules and 'aipictures.reference_analysis' not in sys.modules
'''
    subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).parents[1],check=True,timeout=15)


def test_two_reference_candidate_uses_ordered_conditions_not_output_latent():
    info = model_info(); info['AIPicturesReleaseCompletedEncoders'] = {}
    g, b = flux_klein.build(ImageRequest('unused', '梦核风格', seed=45), info,
                            'identity.png', style_reference='style.png')
    assert g['pos_style']['inputs']['conditioning'] == ['pos_ref', 0]
    assert g['pos_style']['inputs']['latent'] == ['style_encode', 0]
    assert g['guider']['inputs']['positive'] == ['pos_style', 0]
    assert g['release']['inputs']['conditioning'] == ['pos_style', 0]
    assert g['sample']['inputs']['latent_image'] == ['latent', 0]
    assert g['latent']['class_type'] == 'EmptyFlux2LatentImage'
    assert b['reference'] == ['reference'] and b['style_reference'] == ['style_reference']
    assert 'Image 1' in g['text']['inputs']['text'] and 'Image 2' in g['text']['inputs']['text']
    with pytest.raises(ValueError, match='同时提供'):
        flux_klein.build(ImageRequest('unused', '梦核'), info, style_reference='style.png')


def test_smart_flux_keeps_separate_reference_sampler_and_fixed_seed(tmp_path):
    from PIL import Image
    from aipictures.smart_generation import generate
    source=tmp_path/'ref.png';Image.new('RGBA',(64,128),(220,180,40,255)).save(source)
    request=ImageRequest(flux_klein.UNET,'梦核风格','水印',256,256,4,1.,456,'euler','flux2')
    graph,bindings=flux_klein.build(request,model_info(),'__placeholder__')
    params=dict(asdict(request),model_family='flux_klein',bindings=bindings,denoise=1.,
                user_prompt=request.positive,user_negative=request.negative,
                reference_policy='semantic',output_background='preserve')
    client=Mock();client.upload_image.return_value='new_upload.png';client.generate.return_value={'images':[]}
    with patch('aipictures.engine_service.release_idle_models',return_value={}):
        generate(tmp_path,graph,params,None,None,source,client,threading.Event(),lambda *_:None)
    actual=client.generate.call_args.args[0]
    assert actual['reference']['inputs']['image']=='new_upload.png'
    assert actual['guider']['inputs']['positive']==['pos_ref',0]
    assert actual['noise']['inputs']['noise_seed']==456
    assert graph['reference']['inputs']['image']=='__placeholder__'


def test_actual_qt_automatic_routes_and_retired_sdxl():
    result=subprocess.run([sys.executable,'-m','tests.live_reference_routes'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONUTF8='1'),capture_output=True,timeout=40)
    assert result.returncode==0,result.stdout.decode('utf-8','replace')+result.stderr.decode('utf-8','replace')


def test_sdxl_retirement_preserves_changed_and_unlisted_weights(tmp_path):
    root = tmp_path/'checkpoints'; root.mkdir()
    original = root/'verified.safetensors'; original.write_bytes(b'original')
    changed = root/'changed.safetensors'; changed.write_bytes(b'modified')
    other = root/'controlnet.safetensors'; other.write_bytes(b'keep')
    sha = hashlib.sha256(b'original').hexdigest()
    with patch.object(retire_sdxl, 'ALLOWED', {'verified.safetensors': (8, sha), 'changed.safetensors': (8, sha)}):
        result = retire_sdxl.remove([original, changed], [root], tmp_path/'report.json', lambda: None)
    assert not original.exists() and changed.exists() and other.exists()
    assert result['reclaimed_bytes'] == 8 and len(result['skipped']) == 1


def test_hardlinked_checkpoint_names_count_storage_only_once(tmp_path):
    import os
    root=tmp_path/'checkpoints'; root.mkdir()
    a=root/'verified.safetensors'; a.write_bytes(b'original')
    b=root/'copy.safetensors'; os.link(a, b)
    sha=hashlib.sha256(b'original').hexdigest()
    with patch.object(retire_sdxl, 'ALLOWED', {a.name:(8,sha), b.name:(8,sha)}):
        result=retire_sdxl.remove([a,b],[root],tmp_path/'report.json',lambda:None)
    assert result['reclaimed_bytes']==8 and len(result['deleted'])==2
    assert not a.exists() and not b.exists()


def test_retirement_stops_if_queue_became_busy_or_path_is_outside(tmp_path):
    root=tmp_path/'checkpoints'; root.mkdir()
    a=root/'verified.safetensors'; a.write_bytes(b'original')
    sha=hashlib.sha256(b'original').hexdigest()
    def busy(): raise ValueError('backend busy')
    with patch.object(retire_sdxl, 'ALLOWED', {a.name:(8,sha)}):
        with pytest.raises(ValueError, match='backend busy'):
            retire_sdxl.remove([a],[root],tmp_path/'report.json',busy)
        with pytest.raises(ValueError, match='不在明确授权'):
            retire_sdxl.remove([tmp_path/a.name],[root],tmp_path/'report.json',lambda:None)
    assert a.exists()
