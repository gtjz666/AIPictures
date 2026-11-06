"""Optional UI context only; GPU queries always run in a separate process."""
from datetime import datetime
import os
from .gpu_watch import read_json,start
from .storage import write_json


def snapshot(window) -> dict:
    current=window.current;folder=current.get('folder') if current else getattr(window,'importing_folder',None)
    old=read_json(window.api_controller.data/'gpu-watch-context.json')
    return dict(pid=os.getpid(),folder=str(folder) if folder else old.get('folder'),
        state='running' if current else 'preparing' if window.preparing else window.task_display.stage,
        stage=window.task_display.stage,progress=window.progress.value(),maximum=window.progress.maximum(),
        queued_count=len(getattr(window,'pending',[])),
        updated_at=datetime.now().astimezone().isoformat())


def attach(window) -> None:
    data=window.api_controller.data
    if read_json(data/'gpu-watch-settings.json').get('enabled') is not True:return
    from PySide6.QtCore import QTimer
    # Startup is asynchronous: a failed recorder must never prevent creation.
    def launch():
        try:start(data)
        except (OSError,RuntimeError) as exc:
            write_json(data/'gpu-watch-start-error.json',dict(error=str(exc)))
    window.launch(lambda _:launch(),lambda *_:None)
    timer=QTimer(window);timer.setInterval(1000)
    def update():
        try:write_json(data/'gpu-watch-context.json',snapshot(window))
        except OSError:pass
    timer.timeout.connect(update);timer.start();window.gpu_watch_context_timer=timer
    update()
