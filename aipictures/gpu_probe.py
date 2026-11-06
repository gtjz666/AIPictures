"""Read-only NVML worker. No CUDA, Torch, models, tuning or GPU allocations."""
import ctypes as c
import json
import os
from pathlib import Path
import sys
import time


class Memory(c.Structure):
    _fields_ = [('total', c.c_ulonglong), ('free', c.c_ulonglong), ('used', c.c_ulonglong)]


class NvmlError(RuntimeError):
    def __init__(self, code: int):
        self.code = code
        super().__init__(f'NVML query failed: {code}')


class Probe:
    def __init__(self):
        if os.name == 'nt':
            # Never search the working directory for a DLL.
            library = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/nvml.dll'
            self.lib = c.CDLL(str(library))
        else:
            self.lib = c.CDLL('libnvidia-ml.so.1')
        signatures = {
            'nvmlInit_v2': [], 'nvmlShutdown': [],
            'nvmlDeviceGetCount_v2': [c.POINTER(c.c_uint)],
            'nvmlDeviceGetHandleByIndex_v2': [c.c_uint, c.POINTER(c.c_void_p)],
            'nvmlDeviceGetMemoryInfo': [c.c_void_p, c.POINTER(Memory)],
            'nvmlDeviceGetName': [c.c_void_p, c.c_char_p, c.c_uint],
            'nvmlDeviceGetUUID': [c.c_void_p, c.c_char_p, c.c_uint],
            'nvmlSystemGetDriverVersion': [c.c_char_p, c.c_uint],
        }
        for name, args in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes = args; function.restype = c.c_int
        self.check(self.lib.nvmlInit_v2())

    @staticmethod
    def check(code: int) -> None:
        if code: raise NvmlError(code)

    def text(self, name: str, handle=None) -> str:
        buffer = c.create_string_buffer(128)
        args = [buffer, len(buffer)] if handle is None else [handle, buffer, len(buffer)]
        self.check(getattr(self.lib, name)(*args))
        return buffer.value.decode('utf-8', 'replace')

    def sample(self) -> dict:
        count = c.c_uint(); self.check(self.lib.nvmlDeviceGetCount_v2(c.byref(count)))
        if not 0 < count.value <= 32: raise ValueError('NVML did not return a supported GPU count.')
        devices = []
        for index in range(count.value):
            handle = c.c_void_p()
            self.check(self.lib.nvmlDeviceGetHandleByIndex_v2(index, c.byref(handle)))
            memory = Memory(); self.check(self.lib.nvmlDeviceGetMemoryInfo(handle, c.byref(memory)))
            if not 0 <= memory.used <= memory.total or not 0 <= memory.free <= memory.total or not memory.total:
                raise ValueError('Invalid device memory counters; not an OOM diagnosis.')
            devices.append(dict(index=index, uuid=self.text('nvmlDeviceGetUUID', handle),
                name=self.text('nvmlDeviceGetName', handle), total_bytes=memory.total,
                used_bytes=memory.used, free_bytes=memory.free))
        return dict(devices=devices, driver=self.text('nvmlSystemGetDriverVersion'))


def main() -> None:
    probe = None
    for line in sys.stdin:
        if line.strip() != 'sample': continue
        started = time.monotonic()
        try:
            if probe is None: probe = Probe()
            result = dict(status='ok', **probe.sample())
        except Exception as exc:
            result = dict(status='probe_error', error=str(exc)[:300], nvml_code=getattr(exc, 'code', None))
            # Keep a successful NVML initialization balanced. Handles are looked
            # up afresh for each query; never repeatedly increment its refcount.
        result.update(sample_time=time.time(), query_ms=round((time.monotonic()-started)*1000, 2))
        print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
