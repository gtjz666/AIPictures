import itertools
import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import websocket

from aipictures.engine import ComfyClient, Cancelled


def completed():
    return {'mine':{'outputs':{'save':{'images':[{'filename':'result.png','type':'output'}]}}}}


def test_default_does_not_fail_a_busy_model_after_thirty_minutes(tmp_path):
    client=ComfyClient();history_calls=[];posts=[]
    def request(path,body=None,raw=False):
        if path=='/prompt':posts.append(body);return {'prompt_id':'mine'}
        if path=='/queue':return {'queue_running':[[0,'mine']]}
        if path.startswith('/history/'):
            history_calls.append(path)
            return completed() if len(history_calls)==3 else {}
        return b'image'
    client.request=request;ws=Mock();ws.recv.return_value='{}'
    with patch('aipictures.engine.websocket.create_connection',return_value=ws), \
         patch('aipictures.engine.time.monotonic',side_effect=itertools.count(0,1000)):
        result=client.generate({},tmp_path,Mock(),threading.Event())
    assert result['prompt_id']=='mine' and len(posts)==1
    assert json.loads((tmp_path/'monitor.json').read_text(encoding='utf-8'))['state']=='completed'


def test_output_read_timeout_retries_same_artifact_without_resampling(tmp_path):
    client=ComfyClient();posts=[];downloads=[];events=[]
    def request(path,body=None,raw=False):
        if path=='/prompt':posts.append(body);return {'prompt_id':'mine'}
        if path.startswith('/history/'):return completed()
        downloads.append(path)
        if len(downloads)==1:raise TimeoutError('busy')
        return b'exact-original'
    client.request=request;ws=Mock();ws.recv.return_value='{}'
    with patch('aipictures.engine.websocket.create_connection',return_value=ws),patch.object(threading.Event,'wait'):
        result=client.generate({},tmp_path,lambda k,d:events.append(k),threading.Event())
    assert Path(result['images'][0]).read_bytes()==b'exact-original'
    assert len(posts)==1 and len(set(downloads))==1 and 'monitor_waiting' in events
    assert not list(tmp_path.glob('*.part'))


def test_websocket_connection_timeout_can_use_http_history(tmp_path):
    client=ComfyClient();client.request=Mock(side_effect=[{'prompt_id':'mine'},completed(),b'image'])
    with patch('aipictures.engine.websocket.create_connection',side_effect=websocket.WebSocketTimeoutException()):
        result=client.generate({},tmp_path,Mock(),threading.Event())
    assert result['prompt_id']=='mine'
    assert client.request.call_count==3


def test_cancel_does_not_return_until_backend_removes_owned_task(tmp_path):
    client=ComfyClient();client.cancel=Mock();queues=[];events=[];cancel=threading.Event()
    def request(path,body=None,raw=False):
        if path=='/prompt':return {'prompt_id':'mine'}
        if path=='/queue':
            queues.append(path)
            return {'queue_running':[[0,'mine']]} if len(queues)<3 else {'queue_running':[[1,'someone-else']]}
        if path.startswith('/history/'):return {}
        raise AssertionError(path)
    client.request=request;ws=Mock();ws.recv.return_value='{}'
    with patch('aipictures.engine.websocket.create_connection',return_value=ws), \
         patch('aipictures.engine.time.monotonic',side_effect=itertools.count()):
        with pytest.raises(Cancelled,match='确认停止'):
            client.generate({},tmp_path,lambda k,d:events.append(k),cancel,submitted=lambda _:cancel.set())
    client.cancel.assert_called_once_with('mine')
    assert len(queues)==3 and 'cancel_pending' in events


def test_resume_only_reads_existing_id_and_never_submits(tmp_path):
    client=ComfyClient();paths=[]
    def request(path,body=None,raw=False):
        paths.append(path)
        return completed() if path.startswith('/history/') else b'saved-image'
    client.request=request
    result=client.resume('mine',{},tmp_path,Mock(),threading.Event())
    assert result['prompt_id']=='mine' and '/prompt' not in paths


def test_missing_task_after_backend_restart_does_not_wait_forever_or_resubmit(tmp_path):
    client=ComfyClient();paths=[]
    def request(path,body=None,raw=False):
        paths.append(path);return {}
    client.request=request
    with patch('aipictures.engine.time.monotonic',side_effect=itertools.count(0,10)), \
         patch.object(threading.Event,'wait'),pytest.raises(RuntimeError,match='不会自动重新生成'):
        client.resume('missing',{},tmp_path,Mock(),threading.Event())
    assert '/prompt' not in paths and paths.count('/queue')==3
