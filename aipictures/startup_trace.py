"""CPU-only tracing before Comfy/Torch imports; disabled as soon as HTTP is ready.

Executed by run_path in the private backend. Never import Torch or query devices
here: this is intended to observe a hang in those very initialization calls.
"""
import faulthandler
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from datetime import datetime


WATCHED_IMPORTS = frozenset(('torch', 'torch.cuda', 'comfy.utils',
    'comfy.model_management', 'comfy_kitchen', 'comfy_aimdo.control', 'execution', 'nodes'))


class StartupTrace:
    def __init__(self, folder: Path, *, interval: float = 5., dump_after: float = 20.):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.started = time.monotonic()
        self.main_ident = threading.get_ident()
        self.stopped = threading.Event()
        self.lock = threading.RLock()
        self.last_import = None
        self.dump = (self.folder/'startup-stacks.log').open('w', encoding='utf-8')
        try:
            self.record('starting')
            faulthandler.dump_traceback_later(dump_after, repeat=True, file=self.dump)
            sys.addaudithook(self.import_event)
            self.thread = threading.Thread(target=self.watch, name='startup-trace', daemon=True)
            self.thread.start()
        except BaseException:
            self.stopped.set()
            faulthandler.cancel_dump_traceback_later()
            self.dump.close()
            raise

    def record(self, status: str):
        with self.lock:
            frame = sys._current_frames().get(self.main_ident)
            stack = [] if frame is None else [dict(file=x.filename, line=x.lineno, function=x.name)
                for x in traceback.extract_stack(frame)[-16:]]
            value = dict(status=status, pid=os.getpid(), time=datetime.now().astimezone().isoformat(),
                elapsed_seconds=round(time.monotonic()-self.started, 3), last_import=self.last_import,
                main_thread_stack=stack, device_queries=False)
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
                        self.dump.flush()
                        os.fsync(self.dump.fileno())
                    except OSError:
                        pass
                heartbeat = now

    def stop(self, status: str = 'exited_before_ready'):
        with self.lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
            faulthandler.cancel_dump_traceback_later()
            try:
                self.record('ready' if (self.folder/'startup-ready.json').is_file() else status)
                self.dump.flush()
                os.fsync(self.dump.fileno())
            except OSError:
                pass
            finally:
                self.dump.close()


def start(folder, **kwargs):
    return StartupTrace(Path(folder), **kwargs)
