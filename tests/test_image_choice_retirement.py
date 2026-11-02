"""Model isolation, real-validation gates, and bounded managed weight retirement."""
import hashlib
import json
import threading
import os
import subprocess
import sys
import io
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from aipictures import flux_klein
from aipictures.workflow import ImageRequest


def model_info() -> dict:
    info = {name: {} for name in flux_klein.NODES}
    for node, field, name in (('UNETLoader','unet_name',flux_klein.UNET),
                              ('CLIPLoader','clip_name',flux_klein.ENCODER),
                              ('VAELoader','vae_name',flux_klein.VAE)):
        info[node] = {'input': {'required': {field: [[name]]}}}
    return info


@pytest.mark.parametrize('reference', ['', 'chosen.png'])
def test_flux_graph_uses_native_four_step_sampling_and_separate_reference(reference):
    info = model_info();info['AIPicturesReleaseCompletedEncoders'] = {}
    graph, bindings = flux_klein.build(ImageRequest('unused','正视图，白色衬衫','水印',768,1024,seed=45), info, reference)
    assert graph['clip']['inputs']['type'] == 'flux2'
    assert graph['sigmas']['inputs']['steps'] == 4 and graph['guider']['inputs']['cfg'] == 1.
    assert graph['noise']['inputs']['noise_seed'] == 45
    assert graph['sample']['inputs']['latent_image'] == ['latent',0]
    assert graph['guider']['inputs']['model'] == ['release',0]
    assert '正视图，白色衬衫' in graph['text']['inputs']['text']
    assert '水印' in graph['text']['inputs']['text']  # Soft exclusion; no nonexistent CFG negative pass.
    assert ('reference' in graph) == bool(reference)
    assert bindings['reference'] == (['reference'] if reference else [])
    if reference:
        assert graph['reference']['inputs']['image'] == reference
        assert graph['release']['inputs']['conditioning'] == ['pos_ref',0]
        assert graph['pos_ref']['inputs']['latent'] == ['ref_encode',0]
        assert graph['ref_scale']['inputs']['resolution_steps']==1
    assert not any(any(s in n['class_type'].lower() for s in ('lora','controlnet','wan')) for n in graph.values())


def test_flux_does_not_enable_from_model_presence_alone(tmp_path):
    info = model_info()
    assert flux_klein.available(info) and not flux_klein.enabled(info,tmp_path)
    settings = tmp_path/'flux-klein-settings.json'
    settings.write_text(json.dumps({'validated':True}))
    assert flux_klein.enabled(info,tmp_path)
    del info['Flux2Scheduler']
    assert not flux_klein.enabled(info,tmp_path)


@pytest.mark.parametrize('kwargs', [{'width':769}, {'seed':-1}, {'positive':''}, {'lora':'old.safetensors'}])
def test_flux_rejects_invalid_request_without_submission(kwargs):
    values = dict(checkpoint='unused',positive='人物',width=768,height=1024,seed=12)
    values.update(kwargs)
    with pytest.raises(ValueError):
        flux_klein.build(ImageRequest(**values),model_info())


def test_no_wan_fallback_or_comfy_submission_for_retired_video(tmp_path):
    from aipictures.video_generation import generate
    client = Mock()
    with pytest.raises(ValueError,match='已停用'):
        generate(client,tmp_path/'old',{'engine':'wan'},threading.Event(),lambda *_:None)
    client.assert_not_called();client.discover.assert_not_called();client.generate.assert_not_called()


def test_only_receipted_unchanged_managed_weights_are_removed(tmp_path):
    from tools import remove_managed_wan as remover
    root = tmp_path/'models';(root/'diffusion_models').mkdir(parents=True)
    original = b'publisher-original'; checksum = hashlib.sha256(original).hexdigest()
    relative = 'diffusion_models/managed.safetensors'; managed = root/relative
    changed = root/'diffusion_models/changed.safetensors'; unowned = root/'diffusion_models/user.safetensors'
    managed.write_bytes(original);changed.write_bytes(b'changed-file-by-user');unowned.write_bytes(original)
    outside = tmp_path/'outside.safetensors';outside.write_bytes(original)
    rows = [{'path':str(p),'bytes':len(original),'sha256':checksum} for p in (managed,changed,outside)]
    receipt = tmp_path/'receipt.json';receipt.write_text(json.dumps({'files':rows}))
    allowed = {relative:(len(original),checksum), 'diffusion_models/changed.safetensors':(len(original),checksum)}
    guard = Mock()
    with patch.object(remover,'ALLOWED',allowed):
        result = remover.remove([receipt],root,tmp_path/'deleted.json',guard)
    assert result['reclaimed_bytes'] == len(original) and len(result['deleted']) == 1
    guard.assert_called_once()
    assert not managed.exists() and changed.exists() and unowned.exists() and outside.exists()


def test_retirement_stops_if_shared_queue_becomes_busy(tmp_path):
    from tools import remove_managed_wan as remover
    root = tmp_path/'models';root.mkdir()
    path = root/'managed.safetensors';path.write_bytes(b'original')
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = tmp_path/'receipt.json'
    receipt.write_text(json.dumps({'files':[{'path':str(path),'bytes':8,'sha256':sha}]}))
    def busy():raise ValueError('backend busy')
    with patch.object(remover,'ALLOWED',{'managed.safetensors':(8,sha)}),pytest.raises(ValueError,match='busy'):
        remover.remove([receipt],root,tmp_path/'report.json',busy)
    assert path.read_bytes() == b'original'


def test_actual_image_and_h3_only_controls():
    result=subprocess.run([sys.executable,'-m','tests.live_h3_image_choice'],
        cwd=Path(__file__).parents[1],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONUTF8='1'),
        capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout.decode('utf-8','replace')+result.stderr.decode('utf-8','replace')


def test_model_download_resumes_clean_short_response_before_install(tmp_path):
    from tools import prepare_style_models as installer
    class Response(io.BytesIO):
        def __init__(self, body, status, headers):
            super().__init__(body);self.status=status;self.headers=headers
    requests=[]
    def fetch(request,timeout):
        requests.append(request)
        return Response(b'abc',200,{}) if len(requests)==1 else Response(b'def',206,{'Content-Range':'bytes 3-5/6'})
    target=tmp_path/'model.safetensors'
    with patch.object(installer,'urlopen',side_effect=fetch),patch.object(installer.time,'sleep'):
        result=installer.install_file(target,{'bytes':6,'sha256':hashlib.sha256(b'abcdef').hexdigest(),'url':'https://example.test/model'})
    assert target.read_bytes()==b'abcdef' and result['publisher_sha256_verified']
    assert len(requests)==2 and requests[1].get_header('Range')=='bytes=3-'


def test_transient_windows_reader_lock_does_not_lose_progress(tmp_path):
    from aipictures import storage
    target=tmp_path/'monitor.json';target.write_text('{"state":"sampling"}')
    real_replace=storage.os.replace;attempts=[]
    def replace(source,destination):
        attempts.append(1)
        if len(attempts)<3:
            assert json.loads(target.read_text())['state']=='sampling'
            raise PermissionError('temporary sharing lock')
        real_replace(source,destination)
    with patch.object(storage.os,'replace',side_effect=replace),patch.object(storage.time,'sleep') as delay:
        storage.write_json(target,{'state':'completed'})
    assert len(attempts)==3 and delay.call_count==2
    assert json.loads(target.read_text())=={'state':'completed'}
    assert not list(tmp_path.glob('*.tmp'))


def test_persistent_write_denial_preserves_original_record(tmp_path):
    from aipictures import storage
    target=tmp_path/'monitor.json';target.write_text('{"state":"sampling"}')
    with patch.object(storage.os,'replace',side_effect=PermissionError('readonly')),\
         patch.object(storage.time,'sleep'),pytest.raises(PermissionError):
        storage.write_json(target,{'state':'completed'})
    assert json.loads(target.read_text())['state']=='sampling'


def registry_fixture(folder: Path, reference: bool) -> Path:
    from PIL import Image
    folder.mkdir()
    image=folder/'image_000.png';Image.new('RGB',(256,256),(80,120,160)).save(image)
    graph,_=flux_klein.build(ImageRequest('unused','中文描述',seed=3),model_info(),'ref.png' if reference else '')
    result={'prompt_id':'synthetic-protocol-test','images':[str(image)],'image_sha256':[hashlib.sha256(image.read_bytes()).hexdigest()],
            'history':{'status':{'status_str':'success','completed':True},'prompt':[0,'synthetic-protocol-test',graph]}}
    path=folder/'result.json';path.write_text(json.dumps(result))
    return path


def test_registration_requires_both_routes_and_matching_outputs(tmp_path):
    from tools.register_flux_klein import register
    text=registry_fixture(tmp_path/'text',False);ref=registry_fixture(tmp_path/'ref',True)
    config=register(text,ref,tmp_path/'data')
    assert config['validated'] and config['text_default']=='zimage'
    assert len(config['validation_results'])==2
    (ref.parent/'image_000.png').write_bytes(b'changed')
    before=(tmp_path/'data/flux-klein-settings.json').read_bytes()
    with pytest.raises(ValueError,match='已改变'):register(text,ref,tmp_path/'data')
    assert (tmp_path/'data/flux-klein-settings.json').read_bytes()==before


def test_text_result_cannot_stand_in_for_reference_validation(tmp_path):
    from tools.register_flux_klein import register
    text=registry_fixture(tmp_path/'text',False)
    with pytest.raises(ValueError,match='文字/参考路线'):register(text,text,tmp_path/'data')
    assert not (tmp_path/'data/flux-klein-settings.json').exists()
