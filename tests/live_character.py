"""Real identity-reference workflow, compact layout, and explicit missing-pose-model state."""
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QPoint, QTimer
from aipictures.app import Window, create_application
from aipictures.character_profile import load_profile
from aipictures.storage import DATA, write_json
from aipictures.workflow_library import digest
from aipictures.prompt_binding import check_models

os.environ['AIPICTURES_BROWSER_PROFILE'] = str(DATA / 'test-browser' / uuid4().hex)
app = create_application([])
window = Window(); window.show()
profile = load_profile()
state = {'stage': 'connect', 'start': time.monotonic(), 'progress': 0}
original_launch = window.launch


def launch(action, callback):
    def event(kind, data):
        if kind == 'progress': state['progress'] += 1
        callback(kind, data)
    original_launch(action, event)
window.launch = launch


def tick():
    if time.monotonic() - state['start'] > 300: raise TimeoutError(state['stage'])
    if state['stage'] == 'connect' and window.connected:
        window.apply_character(route='baseline'); window.positive.clear()
        graph, params = window.graph_snapshot('__reference__')
        assert 'IPAdapterAdvanced' in [n['class_type'] for n in graph.values()]
        assert not any(n['class_type'] == 'ControlNetLoader' for n in graph.values())
        assert graph['5']['inputs']['denoise'] == .3
        assert graph['2']['inputs']['text'] == profile['positive']
        assert graph['3']['inputs']['text'] == profile['negative']
        assert window.model.mapTo(window, QPoint(0,0)).x() < window.positive.mapTo(window, QPoint(0,0)).x()
        assert not window.gallery.isVisible()
        window.generate_button.click(); state['stage'] = 'upload'
    elif state['stage'] == 'upload' and window.current:
        state['job'] = window.current['folder']; state['stage'] = 'generation'
    elif state['stage'] == 'generation' and not window.current and not window.preparing:
        folder = state['job']
        job = json.loads((folder / 'job.json').read_text('utf-8'))
        assert job['status'] == 'completed', job
        assert window.pixmap.width() == 768 and window.pixmap.height() == 1024
        assert digest(profile['reference']) == profile['source_sha256']
        window.grab().save(str(DATA / 'character-studio.png'))
        window.open_assets(); assert window.assets_dialog.isVisible(); window.assets_dialog.close()
        window.open_skeleton(); state['stage'] = 'skeleton'; state['after'] = time.monotonic() + 1
    elif state['stage'] == 'skeleton' and time.monotonic() > state['after']:
        window.skeleton_dialog.grab().save(str(DATA / 'character-skeleton.png')); window.skeleton_dialog.close()
        window.character_route.setCurrentIndex(1)
        weights = window.info['object_info']['ControlNetLoader']['input']['required']['control_net_name'][0]
        pose_ready = profile['pose_requires'] in weights
        if pose_ready:
            graph, _ = window.graph_snapshot('__reference__')
            check_models(graph, window.info['object_info'])
            assert graph['5']['inputs']['positive'] == ['22', 0]
        else:
            assert profile['pose_requires'] in window.character_summary.text()
            window.generate_button.click()
            assert window.current is None and not window.preparing
            assert profile['pose_requires'] in window.chat_messages[-1]['text']
        write_json(DATA / 'character-acceptance.json', {'passed': True, 'job': str(state['job']),
            'reference_sha256': profile['source_sha256'], 'output': str(state['job'] / 'image_000.png'),
            'progress_events': state['progress'], 'inspector_on_left': True, 'files_in_dialog': True,
            'pose_workflow_dependencies_ready': pose_ready,
            'pose_workflow_prepared_but_blocked': None if pose_ready else profile['pose_requires']})
        window.character_route.setCurrentIndex(0)
        window.timer.stop(); state['stage'] = 'exit'
        print('Character identity workflow passed; pose dependencies checked against the current backend.', flush=True)
    elif state['stage'] == 'exit' and not window.workers:
        app.quit()


def guarded():
    try: tick()
    except Exception as exc:
        print('FAIL', repr(exc), flush=True); app.exit(1)


timer = QTimer(); timer.timeout.connect(guarded); timer.start(250)
sys.exit(app.exec())
