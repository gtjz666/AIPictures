"""Real embedded editor -> modified nodes -> AIPictures queue -> PNG preview."""
import json
import sys
import time
from unittest.mock import patch
from uuid import uuid4
from PySide6.QtCore import QTimer
from aipictures.app import Window, create_application
from aipictures.storage import DATA, write_json

app = create_application([])
window = Window(); window.show()
state = {'stage': 'connect', 'started': time.monotonic(), 'progress_events': 0}
state['saved_path'] = DATA / 'workflows' / ('editor-test-' + uuid4().hex + '.json')
original_launch = window.launch


def observed_launch(action, callback):
    def observed(kind, data):
        if kind == 'progress': state['progress_events'] += 1
        callback(kind, data)
    original_launch(action, observed)
window.launch = observed_launch


def fail(reason):
    print('FAIL: ' + str(reason), flush=True)
    app.exit(1)


def modified(result):
    if not result['ok']:
        fail(result); return
    print('MODIFIED', result['value'], flush=True)
    window.editor.snapshot(inspected)


def inspected(result):
    if not result['ok']:
        fail(result); return
    payload = result['value']
    assert payload['graph']['2']['inputs']['text'] == 'a blue ceramic teapot on a wooden table, studio photography'
    assert payload['graph']['5']['inputs']['steps'] == 4
    assert payload['graph']['5']['inputs']['positive'] == ['2', 0]
    write_json(DATA / 'editor-roundtrip.json', payload)
    state['expected_text'] = payload['graph']['2']['inputs']['text']
    state['stage'] = 'saving'
    with patch('aipictures.workflow_editor.QFileDialog.getSaveFileName', return_value=(str(state['saved_path']), 'JSON (*.json)')):
        window.editor.save_button.click()


def reopened(result):
    if not result['ok']:
        fail(result); return
    payload = result['value']
    assert payload['graph']['2']['inputs']['text'] == state['expected_text']
    assert payload['graph']['5']['inputs']['steps'] == 4
    assert payload['graph']['5']['inputs']['positive'] == ['2', 0]
    saved = json.loads(state['saved_path'].read_text('utf-8'))
    assert {n['id']: n['pos'] for n in saved['nodes']} == {n['id']: n['pos'] for n in payload['workflow']['nodes']}
    state['stage'] = 'render'
    state['render_after'] = time.monotonic() + 4


def loaded(result):
    print('LOADED', result, flush=True)
    if not result['ok']:
        fail(result); return
    window.editor.action('''
        const textNode = app.rootGraph.getNodeById(2);
        textNode.widgets.find(w => w.name === 'text').value = 'a blue ceramic teapot on a wooden table, studio photography';
        const sampler = app.rootGraph.getNodeById(5);
        sampler.widgets.find(w => w.name === 'steps').value = 4;
        sampler.widgets.find(w => w.name === 'seed').value = Math.floor(Math.random() * 1000000000);
        app.canvas.setDirty(true, true);
        return {nodes: app.rootGraph._nodes.length, modified: true};
    ''', modified)


def tick():
    if time.monotonic() - state['started'] > 180:
        fail('timeout, stage=' + state['stage'] + ', ' + window.editor.status.text()); return
    if state['stage'] == 'connect' and window.connected:
        window.reset_graph()
        window.positive.setPlainText('a ceramic teapot, studio photography')
        window.width.setValue(512); window.height.setValue(512); window.steps.setValue(8)
        window.seed.setText('-1')
        window.tabs.setCurrentIndex(1)
        state['stage'] = 'editor'
        print('WAITING for embedded editor', flush=True)
    elif state['stage'] == 'editor' and window.editor.ready:
        state['stage'] = 'load'
        graph, _ = window.graph_snapshot()
        window.editor.load_graph(graph, 'AIPictures-editor-test', loaded)
        print('LOADING graph into embedded canvas', flush=True)
    elif state['stage'] == 'saving' and state['saved_path'].exists() and not window.editor.pending:
        state['stage'] = 'reopening'
        with patch('aipictures.workflow_editor.QFileDialog.getOpenFileName', return_value=(str(state['saved_path']), 'JSON (*.json)')):
            window.editor.import_button.click()
    elif state['stage'] == 'reopening' and not window.editor.pending:
        state['stage'] = 'checking'
        window.editor.snapshot(reopened)
    elif state['stage'] == 'render' and time.monotonic() > state['render_after']:
        window.editor.grab().save(str(DATA / 'workflow-editor.png'))
        state['stage'] = 'run'
        window.editor.run_button.click()
    elif state['stage'] == 'run' and window.current:
        state['folder'] = window.current['folder']
        state['stage'] = 'generation'
        print('SUBMITTED from embedded editor', flush=True)
    elif state['stage'] == 'generation' and not window.current and not window.pending:
        folder = state['folder']
        job = json.loads((folder / 'job.json').read_text('utf-8'))
        if job['status'] != 'completed' or window.pixmap.isNull():
            fail(window.log.toPlainText()); return
        result = {'passed': True, 'job': str(folder), 'width': window.pixmap.width(),
                  'height': window.pixmap.height(), 'progress_events': state['progress_events'],
                  'saved_and_reopened': True, 'layout_preserved': True,
                  'editor_workflow_saved': (folder / 'editor_workflow.json').exists()}
        write_json(DATA / 'editor-acceptance.json', result)
        print(json.dumps(result), flush=True)
        window.timer.stop()
        state['stage'] = 'exit'
    elif state['stage'] == 'exit' and not window.workers:
        app.quit()


timer = QTimer(); timer.timeout.connect(tick); timer.start(250)
sys.exit(app.exec())
