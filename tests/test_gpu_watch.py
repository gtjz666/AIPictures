"""Pressure, real IPC timeout isolation, crash-safe records and private error evidence."""
import ast
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import pytest

from aipictures.gpu_watch import (MIB, InstanceLock, Journal, ProbeProcess, TaskEvidence,
                                 pressure, read_json, report, serve)
from aipictures.storage import write_json


@pytest.mark.parametrize('used,free,level',[(2000,9000,'normal'),(11800,488,'high_pressure'),
    (12200,88,'critical_pressure'),(12170,118,'critical_pressure'),(11700,588,'high_pressure')])
def test_pressure_is_not_oom(used,free,level):
    assert pressure(dict(total_bytes=12288*MIB,used_bytes=used*MIB,free_bytes=free*MIB))==level


def test_explicit_oom_and_cuda_errors_are_separate_and_do_not_read_prompt(tmp_path):
    task=tmp_path/'videos/job';task.mkdir(parents=True)
    evidence=TaskEvidence(tmp_path);evidence.folder=task
    write_json(task/'job.json',dict(prompt='CUDA out of memory',error='OS error 1455'))
    assert evidence.errors()==[]
    write_json(task/'job.json',dict(error='CUDA error: out of memory'))
    assert evidence.errors()[0]['kind']=='allocation_oom_reported'
    assert not evidence.errors()
    write_json(task/'job.json',dict(error='CUDA error: unknown error'))
    assert evidence.errors()[0]['kind']=='cuda_error_reported'


def test_appended_log_fragments_and_redaction(tmp_path):
    task=tmp_path/'videos/job';task.mkdir(parents=True)
    evidence=TaskEvidence(tmp_path);evidence.folder=task
    log=task/'h3.log';log.write_bytes(b'CUDA out of mem')
    assert evidence.errors()==[]
    with log.open('ab') as stream:stream.write(b'ory Bearer secret-token sk-private\n')
    hit=evidence.errors()[0]
    assert 'secret-token' not in hit['message'] and 'sk-private' not in hit['message']


def test_stale_context_cannot_hide_new_task_or_read_outside_cache(tmp_path):
    old=tmp_path/'videos/old';old.mkdir(parents=True)
    write_json(tmp_path/'gpu-watch-context.json',dict(folder=str(old),state='running'))
    os.utime(tmp_path/'gpu-watch-context.json',(1,1))
    current=tmp_path/'videos/new';current.mkdir()
    os.utime(current,(time.time()+1,time.time()+1))
    evidence=TaskEvidence(tmp_path)
    assert evidence.task()['folder']==str(current.resolve())
    assert evidence.task()['context_is_stale']
    write_json(tmp_path/'gpu-watch-context.json',dict(folder=str(tmp_path.parent/'private')))
    other=TaskEvidence(tmp_path);other.task();assert other.folder is None


def test_single_instance_lock_and_release(tmp_path):
    first=InstanceLock(tmp_path)
    with pytest.raises(RuntimeError):InstanceLock(tmp_path)
    first.close();second=InstanceLock(tmp_path);second.close()


def fake_worker(tmp_path,*,hung=False):
    script=tmp_path/'worker.py';counter=tmp_path/'requests.txt'
    script.write_text('''import json,sys,time
for line in sys.stdin:
 with open(sys.argv[1],'a') as out:out.write('request\\n')
 if sys.argv[2]=='hung':time.sleep(30)
 print(json.dumps(dict(status='ok',devices=[dict(uuid='test',total_bytes=12*1024**3,
     used_bytes=11*1024**3,free_bytes=1024**3)],sample_time=time.time())),flush=True)
''',encoding='utf-8')
    from aipictures.gpu_watch import interpreter
    return [interpreter(),str(script),str(counter),'hung' if hung else 'ok'],counter


def test_stalled_driver_never_creates_more_pending_requests(tmp_path):
    command,counter=fake_worker(tmp_path,hung=True)
    probe=ProbeProcess(command)
    try:
        started=time.monotonic()
        for _ in range(5):assert probe.sample(.1)['status']=='driver_query_timeout'
        assert time.monotonic()-started<2
        assert counter.read_text().splitlines()==['request']
    finally:probe.close()
    assert probe.process.poll() is not None


def test_hung_probe_keeps_durable_supervisor_heartbeat(tmp_path):
    command,_=fake_worker(tmp_path,hung=True)
    folder=serve(tmp_path/'data',interval=.1,timeout=.1,duration=.7,command=command)
    result=report(folder)
    assert result['query_errors']>=3 and result['graceful_stop']
    assert result['last_sample']['status']=='driver_query_timeout'


def test_real_pipe_sampler_and_report_survive_truncated_tail(tmp_path):
    command,_=fake_worker(tmp_path)
    folder=serve(tmp_path/'data',interval=.05,timeout=.1,duration=.6,command=command)
    original=report(folder);assert original['samples']>=2 and original['peak_used_bytes']['test']==11*1024**3
    with (folder/'samples_000.jsonl').open('ab') as stream:stream.write(b'{"broken":')
    restored=report(folder)
    assert restored['samples']==original['samples'] and restored['damaged_lines']==1


def test_journal_flushes_every_record_and_retains_rotated_files(tmp_path,monkeypatch):
    import aipictures.gpu_watch as module
    calls=[];real=os.fsync
    monkeypatch.setattr(module.os,'fsync',lambda fd:(calls.append(fd),real(fd)))
    log=Journal(tmp_path/'log',max_bytes=100)
    for i in range(3):log.write('sample',status='driver_query_timeout',sequence=i)
    log.close()
    assert len(calls)==3 and len(list((tmp_path/'log').glob('samples_*.jsonl')))>=3
    assert report(tmp_path/'log')['query_errors']==3


def test_no_cuda_or_torch_imports_and_probe_has_only_read_apis():
    root=Path(__file__).parents[1]/'aipictures'
    for name in ('gpu_probe.py','gpu_watch.py','gpu_watch_ui.py'):
        tree=ast.parse((root/name).read_text('utf-8'))
        names=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        names += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        assert not any(n and n.split('.')[0] in ('torch','pynvml','cupy','numba') for n in names)
    tree=ast.parse((root/'gpu_probe.py').read_text('utf-8'))
    calls={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute) and node.attr.startswith('nvml')}
    assert calls <= {'nvmlInit_v2','nvmlDeviceGetCount_v2','nvmlDeviceGetHandleByIndex_v2','nvmlDeviceGetMemoryInfo'}


def test_ui_snapshot_keeps_last_task_after_generation_without_prompt_or_key(tmp_path):
    from aipictures.gpu_watch_ui import snapshot
    folder=tmp_path/'videos/job'
    window=SimpleNamespace(current=dict(folder=folder,params=dict(prompt='private',api_key='secret')),
        api_controller=SimpleNamespace(data=tmp_path),preparing=False,
        task_display=SimpleNamespace(stage='模型推理'),progress=SimpleNamespace(value=lambda:50,maximum=lambda:100))
    first=snapshot(window);assert first['folder']==str(folder) and 'secret' not in json.dumps(first)
    write_json(tmp_path/'gpu-watch-context.json',first)
    window.current=None;window.task_display.stage='完成'
    assert snapshot(window)['folder']==str(folder)


def test_actual_backend_step_is_recorded_without_prompt_or_url(tmp_path):
    task=tmp_path/'videos/job';task.mkdir(parents=True)
    write_json(tmp_path/'gpu-watch-context.json',dict(folder=str(task)))
    write_json(task/'native_sample/native_result/monitor.json',dict(state='running',node='sample',
        node_type='KSampler',url='private-url',last_progress=dict(value=12,max=20,prompt_id='private-id')))
    context=TaskEvidence(tmp_path).task()
    assert context['native_sample']['progress']==dict(value=12,max=20)
    assert 'private' not in json.dumps(context)


def test_post_generation_recorder_still_checks_backend_liveness(tmp_path):
    task=tmp_path/'videos/job';task.mkdir(parents=True)
    write_json(tmp_path/'gpu-watch-context.json',dict(folder=str(task),state='完成'))
    write_json(task/'native_sample/native-process.json',dict(pid=os.getpid(),status='stopped'))
    evidence=TaskEvidence(tmp_path);context=evidence.task()
    assert context['state']=='完成' and context['backend_processes'][0]['alive'] is True
    next_task=tmp_path/'videos/next';next_task.mkdir()
    write_json(tmp_path/'gpu-watch-context.json',dict(folder=str(next_task),state='running'))
    next_context=evidence.task()
    assert next_context['previous_backend_pids_to_review'][0]['folder']==str(task)
    # A reused PID must be investigated; the monitor never kills it or labels it a proven leak.


def test_sampling_continues_after_generation_has_completed(tmp_path):
    data=tmp_path/'data';write_json(data/'gpu-watch-context.json',dict(state='完成',stage='完成'))
    command,_=fake_worker(tmp_path)
    folder=serve(data,interval=.1,timeout=.1,duration=.6,command=command)
    result=report(folder)
    assert result['samples']>=3
    assert read_json(data/'diagnostics/gpu-watch/current.json')['context']['state']=='完成'


def test_switching_tasks_releases_old_log_reader_metadata(tmp_path):
    first=tmp_path/'videos/first';first.mkdir(parents=True)
    write_json(tmp_path/'gpu-watch-context.json',dict(folder=str(first),queued_count=0))
    evidence=TaskEvidence(tmp_path);evidence.task()
    evidence.offsets['old']=123;evidence.fragments['old']='fragment';evidence.seen['old']=None
    second=tmp_path/'videos/second';second.mkdir()
    write_json(tmp_path/'gpu-watch-context.json',dict(folder=str(second),queued_count=1))
    assert evidence.task()['queued_count']==1
    assert not evidence.offsets and not evidence.fragments and not evidence.seen


def test_actual_qt_optional_startup_and_task_context():
    import subprocess
    result=subprocess.run([sys.executable,'-m','tools.verify_gpu_watch_ui'],cwd=Path(__file__).parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=40)
    assert result.returncode==0,(result.stdout+result.stderr).decode('utf-8','replace')
