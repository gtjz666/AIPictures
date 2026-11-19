"""One CPU export lane alongside the generation queue."""
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QPushButton

from .task_display import TaskDisplay


class ExportTasks(TaskDisplay):
    def __init__(self, window):
        super().__init__(window, export=True)
        self.window = window
        self.cancel = None
        self.paths = ()
        self.cancel_button = QPushButton('取消导出')
        self.cancel_button.clicked.connect(self.cancel_export)
        self.layout().insertWidget(1, self.cancel_button)
        self.cancel_button.hide()

    @property
    def busy(self):
        return self.cancel is not None

    def cancel_export(self):
        if self.cancel is not None:
            self.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText('正在取消导出…')

    def submit(self, title, paths, action, done):
        if self.busy or self.window.cache_busy or self.window._closing:
            return False
        self.cancel = cancel = Event()
        self.paths = tuple(Path(path).resolve() for path in paths if path)
        self.start()
        self.status.setText(title + ' · 正在导出')
        self.status.setToolTip('')
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()

        def event(kind, data):
            if kind in ('selection_stage', 'video_stage'):
                self.status.setToolTip(data['message'])
            elif kind in ('selection_progress', 'video_export_progress'):
                percent = min(95, round(95 * data['value'] / max(1, data['max'])))
                self.progress.setRange(0, 100)
                self.progress.setValue(percent)
            elif kind in ('result', 'error', 'cancelled'):
                self.cancel = None
                self.paths = ()
                self.finish({'result': 'completed', 'error': 'failed', 'cancelled': 'cancelled'}[kind])
                self.status.setText(title + {'result': ' · 完成', 'error': ' · 失败', 'cancelled': ' · 已取消'}[kind])
                self.status.setToolTip('' if kind == 'result' else str(data))
                self.cancel_button.hide()
                done(kind, data)

        self.window.launch(lambda emit: action(cancel, emit), event)
        return True
