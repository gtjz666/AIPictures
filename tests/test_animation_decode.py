import itertools
import json
from pathlib import Path
import threading
from unittest.mock import Mock,patch

import pytest
from aipictures.animation_decode import sampling_workflow,decode_sampled
from aipictures.engine import ComfyClient,Cancelled
from aipictures.pose_animation import video_workflow


def test_sampling_phase_preserves_seed_and_conditions_without_executing_vae_decode():
    full=video_workflow('ref',['pose']*17,'中文动作','排除内容',123,sampler='dpmpp_2m')
    sample=sampling_workflow(full)
    assert sample['11']==full['11'] and sample['8']==full['8']
    assert sample['15']['inputs']['samples']==['12',0]
    assert not any(n['class_type'] in ('SaveImage','VAEDecode') for n in sample.values())
    assert '13' in full and '14' in full


def test_decode_uses_saved_latent_and_native_vae_without_any_sampler(tmp_path):
    latent=tmp_path/'saved.latent';latent.write_bytes(b'completed-sampling')
    client=Mock();client.url='http://127.0.0.1:8188'
    order=[]
    client.upload_image.side_effect=lambda *a,**kw:order.append('upload') or 'AIPictures/latents/saved.latent'
    client.generate.side_effect=lambda *a,**kw:order.append('decode') or {'images':['frame.png'],'prompt_id':'decode-id'}
    with patch('aipictures.animation_decode.release_idle_models',side_effect=lambda *a:order.append('release') or {'released':True}):
        result=decode_sampled(client,{'latents':[str(latent)],'prompt_id':'sample-id'},tmp_path/'decode',Mock(),threading.Event())
    assert order==['release','upload','decode']
    graph=client.generate.call_args.args[0]
    assert {n['class_type'] for n in graph.values()}=={'LoadLatent','VAELoader','VAEDecode','SaveImage'}
    assert result['sampling_prompt_id']=='sample-id' and result['decode_prompt_id']=='decode-id'
    assert result['latents']==[str(latent)]
    assert json.loads((tmp_path/'decode/source.json').read_text('utf-8'))['resampled'] is False


def test_cancel_before_decode_keeps_sampling_and_does_not_submit(tmp_path):
    client=Mock();cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):decode_sampled(client,{},tmp_path/'decode',Mock(),cancel)
    client.generate.assert_not_called();client.upload_image.assert_not_called()


def test_missing_saved_sampling_never_triggers_automatic_regeneration(tmp_path):
    client=Mock()
    with pytest.raises(ValueError,match='不会自动重新生成'):
        decode_sampled(client,{'latents':[]},tmp_path/'decode',Mock(),threading.Event())
    client.generate.assert_not_called()


def test_previously_submitted_decode_is_not_silently_submitted_twice(tmp_path):
    latent=tmp_path/'saved.latent';latent.write_bytes(b'data')
    folder=tmp_path/'decode';folder.mkdir();(folder/'submitted.json').write_text('{}')
    client=Mock()
    with pytest.raises(ValueError,match='避免重复提交'):
        decode_sampled(client,{'latents':[str(latent)]},folder,Mock(),threading.Event())
    client.generate.assert_not_called()


@pytest.mark.parametrize('allow_latent_only',[False,True])
def test_api_requires_explicit_latent_only_opt_in(tmp_path,allow_latent_only):
    client=ComfyClient();calls=[]
    def request(path,body=None,raw=False):
        calls.append(path)
        if path=='/prompt':return {'prompt_id':'mine'}
        if path.startswith('/history/'):
            return {'mine':{'outputs':{'save':{'latents':[{'filename':'data.latent','type':'output'}]}}}}
        if path.startswith('/view?'):return b'exact-saved-latent'
        raise AssertionError(path)
    client.request=request;ws=Mock();ws.recv.return_value='{}'
    with patch('aipictures.engine.websocket.create_connection',return_value=ws), \
         patch('aipictures.engine.time.monotonic',side_effect=itertools.count()):
        if allow_latent_only:
            result=client.generate({},tmp_path,Mock(),threading.Event(),allow_latent_only=True)
            assert result['images']==[]
            assert Path(result['latents'][0]).read_bytes()==b'exact-saved-latent'
        else:
            with pytest.raises(RuntimeError,match='SaveImage'):
                client.generate({},tmp_path,Mock(),threading.Event())
    assert calls.count('/prompt')==1


def test_latent_only_mode_still_rejects_empty_outputs(tmp_path):
    client=ComfyClient()
    client.request=lambda path,*a,**kw:{'prompt_id':'mine'} if path=='/prompt' else {'mine':{'outputs':{}}}
    ws=Mock();ws.recv.return_value='{}'
    with patch('aipictures.engine.websocket.create_connection',return_value=ws), \
         patch('aipictures.engine.time.monotonic',side_effect=itertools.count()),pytest.raises(RuntimeError,match='SaveImage'):
        client.generate({},tmp_path,Mock(),threading.Event(),allow_latent_only=True)
