"""CPU-only tracing before Comfy/Torch imports; disabled as soon as HTTP is ready.

Executed by run_path in the private backend. Never import Torch or query devices
here: this is intended to observe a hang in those very initialization calls.
"""
import json
import os
from pathlib import Path
import sys
import threading
import time
from datetime import datetime


WATCHED_IMPORTS = frozenset(('torch', 'torch.cuda', 'comfy.utils',
    'comfy.model_management', 'comfy_kitchen', 'comfy_aimdo.control', 'execution', 'nodes'))


class StartupTrace:
    def __init__(self, folder: Path, *, interval: float = 5., dump_after: float | None = None):
        # Keep the old keyword for diagnostic callers, but never arm a native
        # traceback timer: it crashes the deployed CPython 3.12.3 on Windows.
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.started = time.monotonic()
        self.main_ident = threading.get_ident()
        self.stopped = threading.Event()
        self.lock = threading.RLock()
        self.last_import = None
        try:
            self.record('starting')
            sys.addaudithook(self.import_event)
            self.thread = threading.Thread(target=self.watch, name='startup-trace', daemon=True)
            self.thread.start()
        except BaseException:
            self.stopped.set()
            raise

    def record(self, status: str):
        with self.lock:
            frame = sys._current_frames().get(self.main_ident)
            # Read live Python frames while holding the GIL. Do not use the
            # asynchronous C all-thread stack walker or read source/locals.
            stack = []
            while frame is not None and len(stack) < 16:
                code = frame.f_code
                stack.append(dict(file=code.co_filename, line=frame.f_lineno, function=code.co_name))
                frame = frame.f_back
            stack.reverse()
            value = dict(status=status, pid=os.getpid(), time=datetime.now().astimezone().isoformat(),
                elapsed_seconds=round(time.monotonic()-self.started, 3), last_import=self.last_import,
                main_thread_stack=stack, device_queries=False, native_traceback_timer=False)
            target = self.folder/'startup-watch.json'
            temp = self.folder/'startup-watch.tmp'
            try:
                with temp.open('w', encoding='utf-8') as output:
                    json.dump(value, output, ensure_ascii=False, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)

    def import_event(self, event, args):
        if self.stopped.is_set() or event != 'import' or not args or args[0] not in WATCHED_IMPORTS:
            return
        with self.lock:
            self.last_import = args[0]
            try:
                self.record('importing')
            except OSError:
                pass  # Diagnostics must not turn an otherwise valid import into a failure.

    def watch(self):
        heartbeat = time.monotonic()
        while not self.stopped.wait(.1):
            if (self.folder/'startup-ready.json').is_file():
                self.stop('ready')
                return
            now = time.monotonic()
            if now-self.started >= 300:
                self.stop('startup_trace_expired')
                return
            if now-heartbeat >= self.interval:
                with self.lock:
                    if self.stopped.is_set():
                        return
                    try:
                        self.record('starting')
                    except OSError:
                        pass
                heartbeat = now

    def stop(self, status: str = 'exited_before_ready'):
        with self.lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
            try:
                self.record('ready' if (self.folder/'startup-ready.json').is_file() else status)
            except OSError:
                pass


def start(folder, **kwargs):
    return StartupTrace(Path(folder), **kwargs)
