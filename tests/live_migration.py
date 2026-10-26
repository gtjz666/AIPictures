"""Open all imported workflows and run only the complete baseline, without changing them."""
import json
import sys
import time
from PySide6.QtCore import QTimer

from aipictures.app import Window, create_application
from aipictures.storage import DATA, write_json
from aipictures.workflow_library import CATALOG, digest, list_workflows, workflow_path, MODEL_WIDGETS

app = create_application([])
window = Window(); window.show()
entries = list_workflows()
assert len(entries) >= 3
state = {'stage': 'connect', 'index': 0, 'started': time.monotonic(), 'loaded': [], 'progress': 0}
original_launch = window.launch


def observed_launch(action, callback):
    def observed(kind, data):
        if kind == 'progress': state['progress'] += 1
        callback(kind, data)
    original_launch(action, observed)
window.launch = observed_launch


def fail(reason):
    print('FAIL', reason, flush=True); app.exit(1)


def guard(fn, *args):
    try: fn(*args)
    except Exception as exc: fail(repr(exc))


def snapshot_received(result):
    if not result['ok']:
        fail(result); return
    entry = entries[state['index']]
    original = json.loads(workflow_path(entry).read_text('utf-8-sig'))
    api = result['value']['graph']
    assert set(api) == {str(n['id']) for n in original['nodes']}
    for node in original['nodes']:
        field = MODEL_WIDGETS.get(node['type']) or ('image' if node['type'] == 'LoadImage' else None)
        if field:
            assert api[str(node['id'])]['inputs'][field] == node['widgets_values'][0], node['type']
        fields = {'CLIPTextEncode': [('text', 0)], 'EmptyLatentImage': [('width', 0), ('height', 1)],
                  'KSampler': [('seed', 0), ('steps', 2), ('cfg', 3), ('sampler_name', 4), ('scheduler', 5)]}
        for field, index in fields.get(node['type'], []):
            assert api[str(node['id'])]['inputs'][field] == node['widgets_values'][index], (node['type'], field)
    # Preserve all original graph links and fixed sampler values.
    for target in original['nodes']:
        for inp in target.get('inputs', []):
            link_id = inp.get('link')
            if link_id is None: continue
            link = next(link for link in original['links'] if link[0] == link_id)
            assert api[str(target['id'])]['inputs'][inp['name']] == [str(link[1]), link[2]]
    write_json(workflow_path(entry).with_name('api_snapshot.json'), api)
    state['loaded'].append(entry['id'])
    print('LOADED', entry['id'], flush=True)
    if state['index'] == 0: state['baseline'] = result['value']
    state['index'] += 1
    state['stage'] = 'next'


def tick():
    if time.monotonic() - state['started'] > 240:
        fail('timeout ' + state['stage']); return
    if state['stage'] == 'connect' and window.connected:
        window.tabs.setCurrentIndex(1); state['stage'] = 'next'
    elif state['stage'] == 'next' and window.editor.ready and not window.editor.pending:
        if state['index'] < 3:
            window.editor.library.setCurrentIndex(state['index'])
            window.editor.library_open_button.click()
            state['stage'] = 'loading'
        else:
            state['stage'] = 'running'
            payload = state['baseline']
            # Execute the imported API exactly as exported; no reduced resolution/steps.
            window.run_editor_graph(payload)
            state['job'] = window.current['folder']
    elif state['stage'] == 'loading' and not window.editor.pending:
        state['stage'] = 'snapshot'
        window.editor.snapshot(lambda result: guard(snapshot_received, result))
    elif state['stage'] == 'running' and not window.current and not window.pending:
        job = json.loads((state['job'] / 'job.json').read_text('utf-8'))
        if job['status'] != 'completed': fail(job); return
        assert window.pixmap.width() == 768 and window.pixmap.height() == 1024
        catalog = json.loads(CATALOG.read_text('utf-8'))
        for entry in catalog['workflows']:
            if entry['id'] in state['loaded']:
                entry['validation']['editor_loaded'] = True
                entry['validation']['api_roundtrip_verified'] = True
                assert digest(entry['source_path']) == entry['source_sha256'] == digest(workflow_path(entry))
            if entry['id'] == entries[0]['id']:
                entry['validation'].update({'generation_verified': True, 'job': str(state['job'].relative_to(DATA))})
        write_json(CATALOG, catalog)
        write_json(DATA / 'migration-acceptance.json', {'passed': True, 'loaded': state['loaded'],
            'baseline_job': str(state['job']), 'width': 768, 'height': 1024,
            'progress_events': state['progress'], 'source_hashes_unchanged': True})
        window.editor.refresh_library()
        window.tabs.setCurrentIndex(1)
        window.editor.library.setCurrentIndex(0)
        window.editor.library_open_button.click()
        state['stage'] = 'capture'; state['capture_after'] = time.monotonic() + 4
        print('GENERATION PASSED', str(state['job']), flush=True)
    elif state['stage'] == 'capture' and time.monotonic() > state['capture_after'] and not window.editor.pending:
        window.grab().save(str(DATA / 'migration-library.png'))
        window.timer.stop(); state['stage'] = 'exit'
    elif state['stage'] == 'exit' and not window.workers:
        app.quit()


timer = QTimer(); timer.timeout.connect(lambda: guard(tick)); timer.start(250)
sys.exit(app.exec())
