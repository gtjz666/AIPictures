"""CPU-only checks: no model loads, real backends, or GPU monitoring."""
import json
import threading
from unittest.mock import Mock

import pytest

from aipictures import backend_connection, motion_native_backend as backend, storage
from aipictures.engine import Cancelled, EngineUnavailable


def fake_backends(monkeypatch, active_url, active):
    monkeypatch.setattr(backend_connection,'local_processes',lambda:[])
    monkeypatch.setattr(backend_connection,'desktop_urls',lambda _: [active_url,active_url+'/'])
    visited=[]
    def client(url):
        visited.append(url)
        if url==active_url:return active
        offline=Mock(url=url)
        offline.request.side_effect=EngineUnavailable(url)
        return offline
    monkeypatch.setattr(backend,'ComfyClient',client)
    return visited


def test_actual_desktop_port_is_checked_once_and_release_is_only_requested(tmp_path,monkeypatch):
    active=Mock();active.request.return_value={}
    visited=fake_backends(monkeypatch,'http://127.0.0.1:9351',active)
    records=backend.release_shared({'url':'http://127.0.0.1:9351/'},folder=tmp_path)
    assert visited.count('http://127.0.0.1:9351')==1
    assert [call.args[0] for call in active.request.call_args_list]==['/queue','/queue','/free']
    active.request.assert_called_with('/free',{'unload_models':True,'free_memory':True})
    assert records[0]['status']=='release_requested'
    saved=json.loads((tmp_path/'shared-release.json').read_text(encoding='utf-8'))
    assert saved['completion_verified'] is False


@pytest.mark.parametrize('failure',['busy','arriving_job','release_error','queue_timeout','invalid_queue'])
def test_uncertain_or_busy_backend_blocks_native_start(tmp_path,monkeypatch,failure):
    active=Mock();requests=[]
    def request(path,*args,**kwargs):
        requests.append(path)
        if path=='/queue':
            if failure=='queue_timeout':raise TimeoutError('test timeout')
            if failure=='invalid_queue':return []
            if failure=='busy' or failure=='arriving_job' and requests.count('/queue')>1:
                return {'queue_running':[['someone-else']]}
            return {}
        if path=='/free' and failure=='release_error':raise OSError('test refused release')
        return {}
    active.request.side_effect=request
    fake_backends(monkeypatch,'http://127.0.0.1:9351',active)
    native=Mock(side_effect=AssertionError('must not start GPU backend'))
    monkeypatch.setattr(backend,'NativeSession',native)
    params={'seconds':2.,'motion_native_settings':{'validated':True}}
    with pytest.raises(ValueError):
        backend.generate(tmp_path,params,threading.Event(),lambda *a:None)
    native.assert_not_called()
    if failure!='release_error':assert '/free' not in requests
    assert '/interrupt' not in requests and '/prompt' not in requests
    saved=json.loads((tmp_path/'shared-release.json').read_text(encoding='utf-8'))
    assert saved['backends'][0]['status'] in ('busy','release_failed','check_failed','invalid_queue')


def test_cancelled_preflight_does_not_discover_or_contact_backends(tmp_path,monkeypatch):
    discovery=Mock(side_effect=AssertionError('must not discover'))
    monkeypatch.setattr(backend_connection,'local_processes',discovery)
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):backend.release_shared({},folder=tmp_path,cancel=cancel)
    discovery.assert_not_called()


def test_durable_write_flushes_before_replace_and_keeps_unicode(tmp_path,monkeypatch):
    events=[];fsync=storage.os.fsync;replace=storage.os.replace
    def flush(fd):events.append('flush');return fsync(fd)
    def rename(source,target):events.append('replace');return replace(source,target)
    monkeypatch.setattr(storage.os,'fsync',flush)
    monkeypatch.setattr(storage.os,'replace',rename)
    target=tmp_path/'monitor.json'
    storage.write_json(target,{'state':'编码完成'},durable=True)
    assert events==['flush','replace']
    assert json.loads(target.read_text(encoding='utf-8'))=={'state':'编码完成'}


def test_flush_failure_preserves_previous_valid_record(tmp_path,monkeypatch):
    target=tmp_path/'monitor.json'
    storage.write_json(target,{'state':'running'})
    def fail(_):raise OSError('test write failure')
    monkeypatch.setattr(storage.os,'fsync',fail)
    with pytest.raises(OSError):storage.write_json(target,{'state':'completed'},durable=True)
    assert json.loads(target.read_text(encoding='utf-8'))=={'state':'running'}
    assert not list(tmp_path.glob('*.tmp'))
