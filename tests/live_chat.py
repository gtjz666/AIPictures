"""Real chat prompt binding + reference upload/img2img + editor synchronization."""
import json
import sys
import time
import os
from io import BytesIO
import numpy as np
from PIL import Image
from uuid import uuid4
from urllib.parse import urlencode
from PySide6.QtCore import QTimer
from aipictures.app import Window, create_application
from aipictures.storage import DATA, write_json
from aipictures.workflow_library import list_workflows, digest

os.environ['AIPICTURES_BROWSER_PROFILE'] = str(DATA / 'test-browser' / uuid4().hex)
app = create_application([])
window = Window(); window.show()
state = {'stage': 'connect', 'start': time.monotonic(), 'progress': 0}
prompt_a = 'a small red robot reading a book, watercolor illustration, white background'
prompt_b = 'a small blue robot reading a book, watercolor illustration, white background'
entry = list_workflows()[0]
source_hash = digest(entry['source_path'])
original_launch = window.launch


def launch(action, callback):
    def events(kind, data):
        if kind == 'progress': state['progress'] += 1
        callback(kind, data)
    original_launch(action, events)
window.launch = launch


def checked_snapshot(result):
    assert result['ok'], result
    graph = result['value']['graph']
    assert graph['2']['inputs']['text'] == prompt_b
    job = json.loads((state['image_job'] / 'workflow.json').read_text('utf-8'))
    load = next(node for node in job.values() if node['class_type'] == 'LoadImage')
    assert any(node['class_type'] == 'LoadImage' and node['inputs']['image'] == load['inputs']['image'] for node in graph.values())
    assert digest(entry['source_path']) == source_hash
    record = {'passed': True, 'text_job': str(state['text_job']), 'image_job': str(state['image_job']),
              'prompt_a': prompt_a, 'prompt_b': prompt_b, 'reference_uploaded': True,
              'editor_prompt_synced': True, 'source_unchanged': True, 'progress_events': state['progress']}
    write_json(DATA / 'chat-acceptance.json', record)
    print(json.dumps(record), flush=True)
    window.timer.stop(); state['stage'] = 'exit'


def tick():
    if time.monotonic() - state['start'] > 180: raise TimeoutError(state['stage'])
    stage = state['stage']
    if stage == 'connect' and window.connected:
        window.workflow_selector.setCurrentIndex(1)
        window.width.setValue(768); window.height.setValue(768); window.steps.setValue(24)
        window.negative.setPlainText('blurry, watermark, text')
        window.seed.setText('-1'); window.positive.setPlainText(prompt_a)
        window.generate_button.click()
        assert window.current
        state['text_job'] = window.current['folder']; state['stage'] = 'text'
    elif stage == 'text' and not window.current:
        folder = state['text_job']
        job = json.loads((folder / 'job.json').read_text('utf-8')); assert job['status'] == 'completed', job
        graph = json.loads((folder / 'workflow.json').read_text('utf-8'))
        assert graph['2']['inputs']['text'] == prompt_a
        assert graph['5']['inputs']['steps'] == 24
        state['first_image'] = window.output
        window.reset_graph(); window.set_reference(window.output)
        window.denoise.setValue(.7); window.positive.setPlainText(prompt_b)
        window.generate_button.click(); state['stage'] = 'upload'
    elif stage == 'upload' and window.current:
        state['image_job'] = window.current['folder']; state['stage'] = 'image'
    elif stage == 'image' and not window.current and not window.preparing:
        folder = state['image_job']
        job = json.loads((folder / 'job.json').read_text('utf-8')); assert job['status'] == 'completed', job
        graph = json.loads((folder / 'workflow.json').read_text('utf-8'))
        assert graph['2']['inputs']['text'] == prompt_b
        assert any(node['class_type'] == 'VAEEncode' for node in graph.values())
        assert graph['5']['inputs']['denoise'] == .7
        name = job['params']['uploaded_reference']
        assert name.startswith('AIPictures/references/')
        raw = window.client.request('/view?' + urlencode({'filename': name.split('/')[-1],
             'subfolder': 'AIPictures/references', 'type': 'input'}), raw=True)
        with Image.open(BytesIO(raw)) as uploaded,Image.open(state['first_image']) as source:
            source=np.asarray(source.convert('RGBA')); uploaded=np.asarray(uploaded.convert('RGB'))
            assert uploaded.shape[:2]==source.shape[:2]
            opaque=source[:,:,3]==255; transparent=source[:,:,3]==0
            assert np.array_equal(uploaded[opaque],source[:,:,:3][opaque])
            assert np.all(uploaded[transparent]==np.array([242,243,245]))
        assert window.pixmap.width() == 768 and window.pixmap.height() == 768
        window.grab().save(str(DATA / 'chat-desktop.png'))
        window.tabs.setCurrentIndex(1); state['stage'] = 'editor'
    elif stage == 'editor' and window.editor.ready and not window.editor.pending and not window.editor_needs_sync:
        state['stage'] = 'snapshot'
        window.editor.snapshot(lambda result: guard(checked_snapshot, result))
    elif stage == 'exit' and not window.workers:
        app.quit()


def guard(fn, *args):
    try: fn(*args)
    except Exception as exc:
        print('FAIL', repr(exc), flush=True); app.exit(1)


timer = QTimer(); timer.timeout.connect(lambda: guard(tick)); timer.start(250)
sys.exit(app.exec())
