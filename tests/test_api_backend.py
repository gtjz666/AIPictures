"""Local HTTP protocol tests use synthetic pixels and fake keys; no paid provider calls."""
import base64
import io
import json
import os
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from aipictures.api_config import ApiSettings, AuthEndpoint, Endpoint, api_base
from aipictures.api_generation import generate_image, parse_plan, plan_art
from aipictures.api_transport import ApiError, list_models, request, run
from aipictures.engine import Cancelled

KEY = 'fake-test-key-no-account'


@pytest.fixture
def api_server():
    image = Image.new('RGBA',(8,12),(72,95,154,255))
    output = io.BytesIO(); image.save(output,format='PNG')
    png = output.getvalue()
    state = {'requests':[], 'png':png, 'encoded':base64.b64encode(png).decode(),
             'plan':{'positive_prompt':'正面红色木箱','negative_prompt':'文字，水印','summary':'按要求制作正面木箱。'},
             'status':200,'delay':0.,'url_result':False,'bad_download':False,'redirect':False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_GET(self): self.handle_request()
        def do_POST(self): self.handle_request()
        def handle_request(self):
            body = self.rfile.read(int(self.headers.get('Content-Length','0')))
            state['requests'].append((self.command,self.path,dict(self.headers),body))
            if self.path=='/image.png':
                status = 500 if state['bad_download'] else 200
                response, kind = png, 'image/png'
            else:
                if state['delay']: time.sleep(state['delay'])
                status = state['status']; kind = 'application/json'
                if self.path.endswith('/models') or self.path.endswith('/models?pageSize=1000'):
                    data = {'data':[{'id':'image-test-model'},{'id':KEY}]}
                elif self.path.endswith('/chat/completions'):
                    content = state['plan']
                    data = {'choices':[{'message':{'content':json.dumps(content,ensure_ascii=False) if isinstance(content,dict) else content,
                        'reasoning_content':'DO NOT SAVE PRIVATE REASONING'},'finish_reason':'stop'}],
                        'usage':{'total_tokens':12,'private':'ignore'}}
                elif ':generateContent' in self.path:
                    data = {'candidates':[{'content':{'parts':[
                        {'thought':True,'inlineData':{'data':'invalid-thought-image'}},
                        {'inlineData':{'mimeType':'image/png','data':state['encoded']}}]}}]}
                else:
                    data = {'data':[{'url':state['url']+'/image.png'} if state['url_result'] else {'b64_json':state['encoded']}]}
                if status!=200: data = {'error':{'message':'provider rejected Bearer '+KEY}}
                response = json.dumps(data).encode()
            if state['redirect']:
                status = 302
            self.send_response(status)
            self.send_header('Content-Type',kind)
            if state['redirect']: self.send_header('Location',state['url']+'/other')
            self.send_header('Content-Length',str(len(response)))
            self.end_headers()
            try: self.wfile.write(response)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads = True
    state['url'] = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=lambda:server.serve_forever(poll_interval=.05),daemon=True)
    thread.start()
    try: yield state
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


def auth(state,**kwargs):
    return AuthEndpoint(Endpoint(state['url']+'/v1','image-test-model',**kwargs),KEY)


def test_models_and_direct_cloud_preserve_chinese(api_server,tmp_path):
    service = auth(api_server)
    assert list_models(service,threading.Event())==['image-test-model']
    result = generate_image(service,tmp_path,'俯视木箱，水彩风格','不要文字',None,threading.Event(),lambda *_:None)
    assert Image.open(result['images'][0]).size==(8,12)
    payload = json.loads(api_server['requests'][-1][3])
    assert payload['n']==1 and '俯视木箱' in payload['prompt'] and '不要文字' in payload['prompt']
    assert 'negative_prompt' not in payload and 'seed' not in payload
    assert result['local_gpu_inference'] is False
    assert KEY not in (tmp_path/'api-request.json').read_text('utf-8')


def test_reference_edits_multipart_and_native_gemini(api_server,tmp_path):
    reference = tmp_path/'source.png'
    Image.new('RGBA',(9,11),(10,20,30,128)).save(reference)
    before = reference.read_bytes()
    for protocol in ('openai','gemini'):
        folder = tmp_path/protocol; folder.mkdir()
        result = generate_image(auth(api_server,protocol=protocol,edits=True),folder,
            '改成正面','',reference,threading.Event(),lambda *_:None)
        assert result['reference_sent']
        method,path,headers,body = api_server['requests'][-1]
        if protocol=='openai':
            assert path.endswith('/images/edits')
            assert 'multipart/form-data' in headers['Content-Type']
            assert b'filename="reference.png"' in body and b'Content-Type: image/png' in body
            assert headers['Authorization']=='Bearer '+KEY
        else:
            assert path.endswith(':generateContent')
            assert headers['x-goog-api-key']==KEY and 'Authorization' not in headers
            payload = json.loads(body)
            encoded = payload['contents'][0]['parts'][1]['inlineData']['data']
            with Image.open(io.BytesIO(base64.b64decode(encoded))) as uploaded:
                assert uploaded.getpixel((0,0))==(10,20,30,128)
            assert len(result['images'])==1  # Thought images never become assets.
    assert reference.read_bytes()==before


def test_image_url_download_does_not_receive_key(api_server,tmp_path):
    api_server['url_result'] = True
    generate_image(auth(api_server),tmp_path,'测试','',None,threading.Event(),lambda *_:None)
    assert len(api_server['requests'])==2
    _,path,headers,_ = api_server['requests'][1]
    assert path=='/image.png' and 'Authorization' not in headers and 'x-goog-api-key' not in headers


@pytest.mark.parametrize('status',[401,403,404,429,500])
def test_failure_is_sanitized_and_never_retried(api_server,tmp_path,status):
    api_server['status'] = status
    with pytest.raises(ApiError) as error:
        generate_image(auth(api_server),tmp_path,'测试','',None,threading.Event(),lambda *_:None)
    assert KEY not in str(error.value)
    assert len(api_server['requests'])==1 and not list(tmp_path.glob('image_*.png'))


def test_download_failure_and_redirect_never_regenerate(api_server,tmp_path):
    api_server.update(url_result=True,bad_download=True)
    with pytest.raises(ApiError,match='下载失败'):
        generate_image(auth(api_server),tmp_path,'test','',None,threading.Event(),lambda *_:None)
    assert sum(row[0]=='POST' for row in api_server['requests'])==1
    api_server['redirect'] = True
    with pytest.raises(ApiError,match='重定向'):
        list_models(auth(api_server),threading.Event())
    assert api_server['requests'][-1][1]=='/v1/models'


def test_planner_json_and_no_private_reasoning(api_server,tmp_path):
    from aipictures.smart_generation import generate
    params = {'user_prompt':'红色木箱','user_negative':'不要水印','output_background':'preserve'}
    result = generate(tmp_path,{},params,auth(api_server),auth(api_server),None,None,threading.Event(),lambda *_:None)
    assert len(result['images'])==1
    assert [row[1] for row in api_server['requests']]==['/v1/chat/completions','/v1/images/generations']
    assert '正面红色木箱' in result['effective_prompt']
    saved = (tmp_path/'plan.json').read_text('utf-8')
    assert 'PRIVATE REASONING' not in saved and KEY not in saved and 'private' not in saved


@pytest.mark.parametrize('plan',['invalid json',{'positive_prompt':'','negative_prompt':'','summary':''},
                                  {'positive_prompt':KEY,'negative_prompt':'','summary':''}])
def test_invalid_plan_stops_before_paid_image_call(api_server,tmp_path,plan):
    from aipictures.smart_generation import generate
    api_server['plan'] = plan
    with pytest.raises(ApiError):
        generate(tmp_path,{}, {'user_prompt':'test','user_negative':'','output_background':'preserve'},
            auth(api_server),auth(api_server),None,None,threading.Event(),lambda *_:None)
    assert len(api_server['requests'])==1
    assert not (tmp_path/'plan.json').exists()


def test_cancel_and_total_timeout_are_prompt_without_retry(api_server):
    api_server['delay'] = 3
    cancel = threading.Event()
    def stop_after_request():
        deadline = time.monotonic()+2
        while not api_server['requests'] and time.monotonic()<deadline:
            time.sleep(.01)
        cancel.set()
    timer = threading.Thread(target=stop_after_request); timer.start()
    started = time.monotonic()
    with pytest.raises(Cancelled): list_models(auth(api_server),cancel)
    timer.join()
    assert time.monotonic()-started<2.5
    with pytest.raises(ApiError,match='超时'):
        run(request(auth(api_server),'/models',require_model=False),threading.Event(),.15)
    assert 1 <= len(api_server['requests']) <= 2  # Timeout may precede socket establishment.


def test_reference_capability_fails_before_network(api_server,tmp_path):
    path = tmp_path/'ref.png'; Image.new('RGBA',(8,8)).save(path)
    with pytest.raises(ValueError,match='未启用'):
        generate_image(auth(api_server),tmp_path,'test','',path,threading.Event(),lambda *_:None)
    assert not api_server['requests']


@pytest.mark.parametrize('url',['http://example.com/v1','https://user:key@example.com/v1',
                               'https://example.com/v1?key=oops','https://example.com/v1/images/generations'])
def test_reject_bad_bases(url):
    with pytest.raises(ValueError): api_base(url)


def test_session_settings_are_not_plaintext_and_are_origin_scoped(tmp_path):
    settings = ApiSettings(tmp_path)
    settings.save('api',False,settings.endpoints,{'image':KEY,'planner':''},{'image':False,'planner':False})
    assert settings.key('image')==KEY
    assert not ApiSettings(tmp_path).key('image')
    assert KEY not in ''.join(path.read_text('utf-8') for path in tmp_path.iterdir())
    assert settings.key('image',Endpoint('https://other.example/v1'))==''
    bad = dict(settings.endpoints,planner=Endpoint('https://example.com/'+KEY))
    with pytest.raises(ValueError,match='包含 Key'):
        settings.save('api',False,bad,{'image':KEY,'planner':''},{})


@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI only')
def test_actual_dpapi_roundtrip_and_forget(tmp_path):
    settings = ApiSettings(tmp_path)
    keys, remember = {'image':KEY,'planner':''}, {'image':True,'planner':False}
    settings.save('api',False,settings.endpoints,keys,remember)
    restored = ApiSettings(tmp_path)
    assert restored.key('image')==KEY
    assert KEY not in restored.vault.read_text('utf-8')
    restored.save('local',False,restored.endpoints,keys,dict(remember,image=False))
    assert not ApiSettings(tmp_path).key('image')


def test_local_plan_binds_real_workflow_without_selecting_lora(api_server,tmp_path):
    from aipictures.workflow import ImageRequest, build_workflow
    from aipictures.prompt_binding import bindings
    from aipictures.smart_generation import generate
    from dataclasses import asdict
    request_value = ImageRequest('sdxl.safetensors','original',lora='manual.safetensors')
    graph = build_workflow(request_value)
    params = dict(asdict(request_value),bindings=bindings(graph),denoise=.6,
        user_prompt='红色木箱',user_negative='水印',output_background='preserve',reference_policy='redraw')
    client = Mock()
    client.generate.return_value = {'images':['existing.png']}
    with patch('aipictures.engine_service.release_idle_models',return_value={}):
        generate(tmp_path,graph,params,auth(api_server),None,None,client,threading.Event(),lambda *_:None)
    actual = client.generate.call_args.args[0]
    mapping = bindings(actual)
    node,field = mapping['positive'][0]
    assert '正面红色木箱' in actual[node]['inputs'][field]
    assert any(node['class_type']=='LoraLoader' and node['inputs']['lora_name']=='manual.safetensors'
               for node in actual.values())
    assert actual[mapping['sampler']]['inputs']['seed']==request_value.seed
    assert len(api_server['requests'])==1
