"""Windows closes this private job on UI exit, terminating only its descendants."""
import os
import threading
from pathlib import Path


def gated_module_command(command: list[str], *, startup_trace: Path | None = None) -> list[str]:
    """Child waits for job assignment; parent death before assignment produces EOF."""
    index=command.index('-m');module=command[index+1]
    gate=("import sys,runpy\n"
          "if sys.stdin.buffer.readline()!=b'go\\n': raise SystemExit(125)\n"
          f"sys.argv=[{module!r},*sys.argv[1:]]\n")
    if startup_trace is None:
        gate += f"runpy.run_module({module!r},run_name='__main__')\n"
    else:
        script = str(Path(__file__).with_name('startup_trace.py').resolve())
        gate += ("_trace=None\n"
                 "try:\n"
                 f" _trace=runpy.run_path({script!r})['start']({str(Path(startup_trace).resolve())!r})\n"
                 "except Exception as exc:\n"
                 " print('Startup diagnostics unavailable:',exc,file=sys.stderr,flush=True)\n"
                 "try:\n"
                 f" runpy.run_module({module!r},run_name='__main__')\n"
                 "finally:\n"
                 " if _trace is not None: _trace.stop()\n")
    return [*command[:index],'-c',gate,*command[index+2:]]


class OwnedProcessJob:
    def __init__(self,pid: int):
        self.handle=None;self.lock=threading.Lock()
        if os.name!='nt':return
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_=[('process_time',c.c_longlong),('job_time',c.c_longlong),('flags',w.DWORD),
                ('minimum',c.c_size_t),('maximum',c.c_size_t),('active',w.DWORD),
                ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class Counters(c.Structure):
            _fields_=[(n,c.c_ulonglong) for n in ('read','write','other','read_bytes','write_bytes','other_bytes')]
        class Limits(c.Structure):
            _fields_=[('basic',Basic),('io',Counters),('process_memory',c.c_size_t),
                ('job_memory',c.c_size_t),('peak_process',c.c_size_t),('peak_job',c.c_size_t)]
        api=c.WinDLL('kernel32',use_last_error=True)
        api.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];api.CreateJobObjectW.restype=w.HANDLE
        api.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];api.SetInformationJobObject.restype=w.BOOL
        api.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];api.OpenProcess.restype=w.HANDLE
        api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];api.AssignProcessToJobObject.restype=w.BOOL
        api.CloseHandle.argtypes=[w.HANDLE];api.CloseHandle.restype=w.BOOL
        handle=api.CreateJobObjectW(None,None)
        if not handle:raise c.WinError(c.get_last_error())
        try:
            limits=Limits();limits.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not api.SetInformationJobObject(handle,9,c.byref(limits),c.sizeof(limits)):
                raise c.WinError(c.get_last_error())
            process=api.OpenProcess(0x0100|0x0001,False,pid)  # SET_QUOTA | TERMINATE
            if not process:raise c.WinError(c.get_last_error())
            try:
                if not api.AssignProcessToJobObject(handle,process):raise c.WinError(c.get_last_error())
            finally:api.CloseHandle(process)
        except BaseException:
            api.CloseHandle(handle);raise
        self.handle=handle;self.api=api

    def close(self):
        with self.lock:
            handle,self.handle=self.handle,None
        if handle:self.api.CloseHandle(handle)
