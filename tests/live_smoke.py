"""Real desktop integration: submit using Window.enqueue, wait, verify saved PNG and preview."""
import json
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from aipictures.app import Window, create_application
from aipictures.storage import DATA

app = create_application([])
window = Window(); window.show()
state = {'submitted': False, 'ticks': 0, 'progress_events': 0}
original_launch = window.launch
def observed_launch(action, callback):
    def observed(kind, data):
        if kind == 'progress': state['progress_events'] += 1
        callback(kind, data)
    original_launch(action, observed)
window.launch = observed_launch


def tick():
    state['ticks'] += 1
    if state['ticks'] > 900:
        print('TIMEOUT', flush=True); app.exit(2); return
    if window.connected and not state['submitted']:
        window.width.setValue(768); window.height.setValue(768)
        window.steps.setValue(20); window.seed.setText('-1')
        window.positive.setPlainText('a cozy wooden cabin beside a lake, autumn forest, golden sunset, detailed digital painting')
        state['submitted'] = True; window.enqueue()
        print('SUBMITTED through desktop window', flush=True)
    if state['submitted'] and window.current is None and not window.pending:
        if window.output and not window.pixmap.isNull() and state['progress_events'] > 0:
            path = Path(window.output)
            window.grab().save(str(DATA / 'acceptance-desktop.png'))
            result = {'image': str(path), 'width': window.pixmap.width(), 'height': window.pixmap.height(),
                      'preview_verified': True, 'progress_events': state['progress_events'],
                      'responsive_timer_ticks': state['ticks'], 'progress': window.progress.value(), 'log': window.log.toPlainText()}
            (DATA / 'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
            print(json.dumps(result, ensure_ascii=False), flush=True); app.exit(0)
        else:
            print(window.log.toPlainText(), flush=True); app.exit(1)


timer = QTimer(); timer.timeout.connect(tick); timer.start(1000)
sys.exit(app.exec())
