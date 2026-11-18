"""One CPU export lane alongside the generation queue."""
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QProgressDialog

from .task_display import TaskDisplay


class ExportTasks(TaskDisplay):
    def __init__(self, window):
        super().__init__(window, export=True)
        self.window = window
        self.cancel = None
        self.paths = ()
        self.hide()

    @property
    def busy(self):
        return self.cancel is not None

    def submit(self, title, paths, action, done, *, popup=False):
        if self.busy or self.window.cache_busy or self.window._closing:
            return False
        self.cancel = cancel = Event()
        self.paths = tuple(Path(path).resolve() for path in paths if path)
        self.start()
        self.progress.setRange(0, 0)
        self.status.setText(title + ' · 正在导出')
        self.status.setToolTip('')
        self.show()
        dialog = None
        if popup:
            dialog = QProgressDialog(title + '…', '取消导出', 0, 0, self.window)
            dialog.setWindowTitle('正在导出')
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setAutoClose(False)
            dialog.setAutoReset(False)
            dialog.setMinimumDuration(0)
            dialog.canceled.connect(cancel.set)
            dialog.show()

        def event(kind, data):
            if kind in ('selection_stage', 'video_stage'):
                self.status.setToolTip(data['message'])
                if dialog and dialog.isVisible():
                    dialog.setLabelText(data['message'])
            elif kind in ('selection_progress', 'video_export_progress'):
                percent = min(95, round(95 * data['value'] / max(1, data['max'])))
                self.progress.setRange(0, 100)
                self.progress.setValue(percent)
                if dialog and dialog.isVisible() and not cancel.is_set():
                    dialog.setRange(0, 100)
                    dialog.setValue(self.progress.value())
            elif kind in ('result', 'error', 'cancelled'):
                self.cancel = None
                self.paths = ()
                self.finish({'result': 'completed', 'error': 'failed', 'cancelled': 'cancelled'}[kind])
                self.status.setText(title + {'result': ' · 完成', 'error': ' · 失败', 'cancelled': ' · 已取消'}[kind])
                if kind != 'result':
                    self.status.setToolTip(str(data))
                if dialog:
                    dialog.hide()
                    dialog.deleteLater()
                done(kind, data)

        self.window.launch(lambda emit: action(cancel, emit), event)
        return True
