"""Verify failed tasks do not block the next queued task, using real ComfyUI."""
import json
import sys
from PySide6.QtCore import QTimer
from aipictures.app import Window, create_application
from aipictures.workflow import ImageRequest, build_workflow
from aipictures.storage import DATA, write_json

app = create_application([])
window = Window(); window.show()
state = {'submitted': False, 'folders': [], 'ticks': 0}


def tick():
    state['ticks'] += 1
    if state['ticks'] > 120: app.exit(2); return
    if window.connected and not state['submitted']:
        state['submitted'] = True
        bad = build_workflow(ImageRequest('missing-test-checkpoint.safetensors', 'test'))
        window.custom_graph = bad; window.enqueue()
        state['folders'].append(window.current['folder'])
        window.custom_graph = None
        window.width.setValue(256); window.height.setValue(256); window.steps.setValue(2)
        for seed in ('111234', '111235'):
            window.seed.setText(seed); window.enqueue()
            state['folders'].append(window.pending[-1][2])
    if state['submitted'] and window.current is None and not window.pending:
        states = [json.loads((folder / 'job.json').read_text('utf-8'))['status'] for folder in state['folders']]
        passed = states == ['failed', 'completed', 'completed']
        write_json(DATA / 'queue-test.json', {'passed': passed, 'states': states})
        print(states, flush=True); app.exit(0 if passed else 1)


timer = QTimer(); timer.timeout.connect(tick); timer.start(1000)
sys.exit(app.exec())
