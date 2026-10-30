"""Qt notifications from disposable daemon work; window closure never joins inference."""
import threading
from PySide6.QtCore import QObject, Signal


class Worker(QObject):
    event = Signal(str, object)
    finished = Signal()

    def __init__(self, action):
        super().__init__()
        self.action = action
        self.detached = False
        self.thread = threading.Thread(target=self.run, daemon=True, name='AIPictures-worker')

    def notify(self, kind, data):
        if not self.detached:
            try: self.event.emit(kind, data)
            except RuntimeError: pass  # QApplication may already have exited.

    def run(self):
        from .engine import Cancelled
        try: self.notify('result', self.action(self.notify))
        except Cancelled as exc: self.notify('cancelled', str(exc))
        except Exception as exc: self.notify('error', str(exc))
        finally:
            if not self.detached:
                try: self.finished.emit()
                except RuntimeError: pass

    def start(self): self.thread.start()
    def isRunning(self): return self.thread.is_alive()
    def detach(self): self.detached = True
