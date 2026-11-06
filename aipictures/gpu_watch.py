"""Independent, durable GPU-memory recorder, with bounded driver calls."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from uuid import uuid4

from .storage import write_json

MIB = 1024**2
OOM = re.compile(r'CUDA(?: error:)? out of memory|torch\.OutOfMemoryError|torch\.cuda\.OutOfMemoryError|'
                 r'CUDA_ERROR_OUT_OF_MEMORY|cudaErrorMemoryAllocation|显存不足', re.I)
ERRORS = re.compile(r'CUDA error:|GPU has fallen off|device lost|device-side assert', re.I)


def interpreter() -> str:
    # The Windows venv redirector can spawn a different PID. These modules use
    # only the stdlib; launching the base interpreter also avoids that wrapper.
    return getattr(sys,'_base_executable',None) or sys.executable


def process_alive(pid: int) -> bool | None:
    """Read process state only. Never terminate a generation process."""
    if type(pid) is not int or pid<=0:return None
    if os.name=='nt':
        import ctypes as c
        from ctypes import wintypes as w
        api=c.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];api.OpenProcess.restype=w.HANDLE
        api.GetExitCodeProcess.argtypes=[w.HANDLE,c.POINTER(w.DWORD)];api.GetExitCodeProcess.restype=w.BOOL
        api.CloseHandle.argtypes=[w.HANDLE];api.CloseHandle.restype=w.BOOL
        handle=api.OpenProcess(0x1000,False,pid)
        if not handle:return False if c.get_last_error()==87 else None
        try:
            code=w.DWORD()
            return code.value==259 if api.GetExitCodeProcess(handle,c.byref(code)) else None
        finally:api.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return None


def read_json(path: Path, limit: int = 64*1024) -> dict:
    try:
        if path.stat().st_size > limit: return {}
        value = json.loads(path.read_text('utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError): return {}


def pressure(device: dict) -> str:
    """Pressure is a warning, never proof that an allocation has failed."""
    total, used, free = (device[k] for k in ('total_bytes','used_bytes','free_bytes'))
    if total <= 0 or not 0 <= used <= total or not 0 <= free <= total:
        return 'unknown'
    if free <= 128*MIB or used/total >= .99: return 'critical_pressure'
    if free <= 512*MIB or used/total >= .95: return 'high_pressure'
    return 'normal'


class InstanceLock:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.file = (root/'instance.lock').open('a+b')
        if self.file.seek(0, 2) == 0: self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close(); raise RuntimeError('显存记录进程已在运行。') from None

    def close(self): self.file.close()


class Journal:
    def __init__(self, folder: Path, max_bytes: int = 8*1024**2):
        self.folder = folder; folder.mkdir(parents=True, exist_ok=False)
        self.index = 0; self.max_bytes = max_bytes; self.file = None; self.open()

    def open(self):
        self.file = (self.folder/f'samples_{self.index:03d}.jsonl').open('a', encoding='utf-8')

    def write(self, event: str, **value):
        record = dict(event=event, time=datetime.now().astimezone().isoformat(),
                      monotonic=round(time.monotonic(),6), **value)
        self.file.write(json.dumps(record, ensure_ascii=False, separators=(',',':'))+'\n')
        self.file.flush(); os.fsync(self.file.fileno())
        if self.file.tell() >= self.max_bytes:
            self.file.close(); self.index += 1; self.open()

    def close(self): self.file.close()


class ProbeProcess:
    """At most one outstanding NVML request; a stuck driver cannot block the recorder."""
    def __init__(self, command: list[str] | None = None):
        command = command or [interpreter(), '-m', 'aipictures.gpu_probe']
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1,
            cwd=str(Path(__file__).resolve().parents[1]),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        from .owned_process import OwnedProcessJob
        try:self.owner=OwnedProcessJob(self.process.pid)
        except OSError:
            self.process.terminate()
            raise RuntimeError('无法建立采集进程退出保护，已停止本次记录。') from None
        self.responses = queue.Queue(maxsize=2); self.pending = False; self.requested = 0.
        self.reader = threading.Thread(target=self.read, daemon=True); self.reader.start()

    def read(self):
        try:
            for line in self.process.stdout:
                if len(line)>16384: continue
                try: value=json.loads(line)
                except ValueError: continue
                if isinstance(value,dict): self.responses.put(value)
        finally:
            try: self.responses.put_nowait(dict(status='probe_exited',returncode=self.process.poll()))
            except queue.Full: pass

    def sample(self, timeout: float) -> dict:
        if not self.pending:
            try:
                self.process.stdin.write('sample\n'); self.process.stdin.flush()
            except (OSError, ValueError): return dict(status='probe_exited',returncode=self.process.poll())
            self.pending=True; self.requested=time.monotonic()
        try:
            result=self.responses.get(timeout=timeout)
            self.pending=False
            result['response_wait_ms']=round((time.monotonic()-self.requested)*1000,2)
            return result
        except queue.Empty:
            return dict(status='driver_query_timeout',waiting_seconds=round(time.monotonic()-self.requested,2),
                        probe_pid=self.process.pid)

    def close(self):
        self.owner.close()
        try:
            self.process.terminate(); self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:pass
        except OSError:pass
        for stream in (self.process.stdin,self.process.stdout):
            # Do not close a pipe while the reader holds its lock in a stalled read.
            if stream is self.process.stdin:
                try:stream.close()
                except OSError:pass


class TaskEvidence:
    """Bounded local job metadata + appended error lines; no prompts or credentials."""
    def __init__(self, data: Path):
        self.data=data.resolve(); self.started=time.time(); self.folder=None
        self.next_discovery=0.; self.offsets={}; self.fragments={}; self.seen={};self.tracked={}

    def task(self) -> dict:
        context=read_json(self.data/'gpu-watch-context.json')
        try:age=max(0,time.time()-(self.data/'gpu-watch-context.json').stat().st_mtime)
        except OSError:age=None
        candidate=Path(context['folder']) if context.get('folder') and age is not None and age<5 else None
        if candidate is None and time.monotonic()>=self.next_discovery:
            self.next_discovery=time.monotonic()+5
            choices=[]
            for name in ('videos','jobs','intent'):
                try:
                    choices.extend(p for p in (self.data/name).iterdir() if p.is_dir())
                except OSError:pass
            if choices: candidate=max(choices,key=lambda p:p.stat().st_mtime)
        if candidate:
            resolved=candidate.resolve()
            if any(resolved.is_relative_to(self.data/name) for name in ('videos','jobs','intent','animations')):
                if resolved!=self.folder:
                    self.offsets.clear();self.fragments.clear();self.seen.clear()
                self.folder=resolved
        info={k:context[k] for k in ('pid','state','stage','progress','maximum','queued_count','updated_at') if k in context}
        if self.folder: info['folder']=str(self.folder)
        if self.folder:
            for phase in ('native_encode','native_sample'):
                path=self.folder/phase/'native_result/monitor.json'
                monitor=read_json(path)
                if monitor:
                    progress=monitor.get('last_progress') or {}
                    info[phase]={k:monitor[k] for k in ('state','node','node_type') if k in monitor}
                    info[phase]['progress']={k:progress[k] for k in ('value','max') if k in progress}
            processes=[]
            for phase,name in (('encoding','native_encode/native-process.json'),
                               ('sampling','native_sample/native-process.json'),('plain_h3','h3-process.json')):
                record=read_json(self.folder/name)
                if type(record.get('pid')) is int:
                    entry=dict(phase=phase,pid=record['pid'],recorded_status=record.get('status'),folder=str(self.folder))
                    self.tracked[(str(self.folder),phase,record['pid'])]=entry
                    processes.append(dict(entry,alive=process_alive(record['pid'])))
            if processes:info['backend_processes']=processes
        retained=[]
        for key,entry in list(self.tracked.items()):
            alive=process_alive(entry['pid'])
            if alive is False:self.tracked.pop(key);continue
            if entry['recorded_status']=='stopped' or entry['folder']!=str(self.folder):
                retained.append(dict(entry,alive=alive,identity_not_verified=True))
        if retained:info['previous_backend_pids_to_review']=retained
        # Bound diagnostic metadata even if access to many old PIDs is denied.
        while len(self.tracked)>128:self.tracked.pop(next(iter(self.tracked)))
        if context:
            info['context_age_seconds']=round(age,1) if age is not None else None
            info['context_is_stale']=age is None or age>=5
        return info

    def errors(self) -> list[dict]:
        if self.folder is None:return []
        hits=[]
        for name in ('job.json','video.json','failure.json','native_encode/native.log','native_sample/native.log',
                     'native_encode/native_result/monitor.json','native_sample/native_result/monitor.json',
                     'animation.engine.log','animation.encoding.log','h3.log'):
            path=self.folder/name
            try:
                stat=path.stat()
                # NTFS metadata/clock precision can put a newly created log a
                # fraction of a second before time.time(); retain this boundary.
                if stat.st_mtime<self.started-1:continue
                if path.suffix=='.json':
                    data=read_json(path,256*1024);text=str(data.get('error') or data.get('exception') or '')
                else:
                    position=self.offsets.get(str(path),max(0,stat.st_size-16384))
                    if position>stat.st_size:position=0;self.fragments.pop(str(path),None)
                    with path.open('rb') as handle:
                        handle.seek(position);raw=handle.read(16384);self.offsets[str(path)]=handle.tell()
                    text=self.fragments.get(str(path),'')+raw.decode('utf-8','replace')
                    self.fragments[str(path)]=text.rsplit('\n',1)[-1][-512:] if not text.endswith('\n') else ''
            except OSError:continue
            for line in text.splitlines():
                kind='allocation_oom_reported' if OOM.search(line) else 'cuda_error_reported' if ERRORS.search(line) else None
                if not kind:continue
                # Strip token-shaped strings even from exceptional engine output.
                excerpt=re.sub(r'(?i)(bearer\s+\S+|sk-[A-Za-z0-9_-]+)', '[redacted]', line)[:400]
                key=(str(path),kind,excerpt)
                if key in self.seen:continue
                self.seen[key]=None
                if len(self.seen)>2048:self.seen.pop(next(iter(self.seen)))
                hits.append(dict(kind=kind,file=str(path),message=excerpt,source_mtime=stat.st_mtime))
        return hits


def serve(data: Path, *, interval: float = 1., timeout: float = 1.5,
          duration: float = 0., command: list[str] | None = None, launch_id: str | None = None) -> Path:
    data=Path(data).resolve();root=data/'diagnostics/gpu-watch';lock=InstanceLock(root)
    token=uuid4().hex;folder=root/(datetime.now().strftime('%Y%m%d_%H%M%S_')+token[:8])
    journal=Journal(folder);probe=None;started=time.monotonic();evidence=TaskEvidence(data)
    summary=dict(schema_version=1,session=token,launch_id=launch_id,pid=os.getpid(),folder=str(folder),status='running',
        interval_seconds=interval,samples=0,query_errors=0,oom_reports=0,peak_used_bytes={},last_pressure={},
        limits='Device aggregate, sampled; WDDM per-process allocation and sub-second peaks are not guaranteed.')
    state=root/'current.json';stopping=False;last_context=None
    try:
        journal.write('started',pid=os.getpid(),interval_seconds=interval,read_only=True)
        write_json(state,summary,durable=True)
        probe=ProbeProcess(command)
        while True:
            tick=time.monotonic()
            if read_json(root/'stop.json').get('session')==token:
                stopping=True;break
            if duration and tick-started>=duration:stopping=True;break
            context=evidence.task()
            stable={k:v for k,v in context.items() if k not in ('updated_at','context_age_seconds')}
            if stable!=last_context:journal.write('task_context',context=context);last_context=stable
            sample=probe.sample(timeout)
            if sample.get('status')=='ok':
                summary['samples']+=1
                for device in sample['devices']:
                    identity=device['uuid'];level=pressure(device);device['pressure']=level
                    summary['peak_used_bytes'][identity]=max(device['used_bytes'],summary['peak_used_bytes'].get(identity,0))
                    if level!=summary['last_pressure'].get(identity):
                        journal.write('pressure_change',gpu=identity,level=level,not_oom_proof=True)
                    summary['last_pressure'][identity]=level
            else:summary['query_errors']+=1
            journal.write('sample',**sample)
            for hit in evidence.errors():
                summary['oom_reports']+=hit['kind']=='allocation_oom_reported'
                journal.write('task_error',**hit)
            summary.update(last_sample=sample,heartbeat=datetime.now().astimezone().isoformat(),context=context)
            write_json(state,summary)
            # No second request is sent while a driver call is outstanding.
            if sample.get('status')=='probe_exited':break
            time.sleep(max(0,interval-(time.monotonic()-tick)))
    finally:
        summary['status']='stopped' if stopping else 'interrupted'
        journal.write('stopped',reason=summary['status'])
        write_json(folder/'summary.json',summary,durable=True)
        write_json(state,summary,durable=True)
        if probe:probe.close()
        journal.close();lock.close()
    return folder


def running(root: Path) -> bool:
    try:lock=InstanceLock(root)
    except RuntimeError:return True
    lock.close();return False


def start(data: Path) -> dict:
    root=Path(data).resolve()/'diagnostics/gpu-watch'
    if running(root):return read_json(root/'current.json')
    launch_id=uuid4().hex
    log=(root/'launcher.log').open('ab')
    flags=(subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else 0
    try:
        process=subprocess.Popen([interpreter(),'-m','aipictures.gpu_watch','run','--data',str(Path(data).resolve()),'--launch-id',launch_id],
            cwd=str(Path(__file__).resolve().parents[1]),stdin=subprocess.DEVNULL,stdout=log,stderr=log,
            creationflags=flags,start_new_session=os.name!='nt')
    finally:log.close()
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        value=read_json(root/'current.json')
        if value.get('launch_id')==launch_id and value.get('status')=='running':return value
        if process.poll() is not None:break
        time.sleep(.05)
    raise RuntimeError('显存记录进程没有完成启动，请查看 diagnostics/gpu-watch/launcher.log。')


def report(folder: Path) -> dict:
    result=dict(folder=str(folder),samples=0,query_errors=0,reported_oom=[],other_cuda_errors=[],
                peak_used_bytes={},last_sample=None,graceful_stop=False,damaged_lines=0,
                conclusion='高占用不等于OOM；没有OOM报错也不能排除采样间的瞬时分配失败。')
    for path in sorted(folder.glob('samples_*.jsonl')):
        with path.open(encoding='utf-8',errors='replace') as stream:
            for line in stream:
                try:row=json.loads(line)
                except ValueError:result['damaged_lines']+=1;continue
                if row.get('event')=='sample':
                    result['last_sample']=row
                    if row.get('status')=='ok':
                        result['samples']+=1
                        for device in row['devices']:
                            key=device['uuid'];result['peak_used_bytes'][key]=max(device['used_bytes'],result['peak_used_bytes'].get(key,0))
                    else:result['query_errors']+=1
                elif row.get('event')=='task_error':
                    key='reported_oom' if row['kind']=='allocation_oom_reported' else 'other_cuda_errors'
                    result[key].append(row)
                    if len(result[key])>1000:result[key].pop(0)
                elif row.get('event')=='stopped':result['graceful_stop']=True
    if not result['graceful_stop']:
        result['session_note']='运行中或缺少正常停止尾记；不能仅据此认定整机崩溃。'
    write_json(folder/'report.json',result,durable=True)
    return result


def main():
    parser=argparse.ArgumentParser(description='AlI显存记录：只读、不自动取消或重试生成。')
    parser.add_argument('action',choices=('start','run','status','stop','report'))
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=0)
    parser.add_argument('--session',type=Path)
    parser.add_argument('--launch-id')
    args=parser.parse_args();root=args.data.resolve()/'diagnostics/gpu-watch'
    if args.action=='run':
        if not 0<=args.duration<=86400:parser.error('duration应在0–86400秒，0为持续记录。')
        serve(args.data,duration=args.duration,launch_id=args.launch_id);return
    if args.action=='start':
        write_json(args.data/'gpu-watch-settings.json',dict(enabled=True))
        value=start(args.data)
    elif args.action=='stop':
        write_json(args.data/'gpu-watch-settings.json',dict(enabled=False))
        value=read_json(root/'current.json')
        if value and running(root):write_json(root/'stop.json',dict(session=value['session']),durable=True)
        value=dict(stop_requested=True,session=value.get('session'))
    elif args.action=='report':
        selected=args.session or Path(read_json(root/'current.json').get('folder',''))
        if not selected.resolve().is_relative_to(root) or not selected.is_dir():
            parser.error('找不到此目录下的显存记录，请先启动或用--session指定已有会话目录。')
        value=report(selected)
    else:value=dict(running=running(root),**read_json(root/'current.json'))
    print(json.dumps(value,ensure_ascii=True))


if __name__=='__main__':main()
