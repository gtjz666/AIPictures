"""Deploy character pose workflows into the connected local backend and local library."""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QTimer
from aipictures.app import Window, create_application
from aipictures.character_profile import load_profile, PROFILE_FILE
from aipictures.engine import ComfyClient
from aipictures.prompt_binding import check_models
from aipictures.storage import DATA, write_json
from aipictures.workflow_library import CATALOG, digest, inspect_workflow, list_workflows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8188')
    parser.add_argument('--test-pose', choices=['stand','reach'], default='stand')
    args = parser.parse_args()
    client = ComfyClient(args.url)
    profile = load_profile()
    if not profile: raise ValueError('请先安装角色参考与骨骼预设')
    info = client.request('/object_info')
    for pose in profile['poses'].values(): check_models(json.loads(Path(pose['graph']).read_text('utf-8')), info)
    pack = DATA / 'workflows' / 'imported' / ('character_controlnet_' + datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:6])
    pack.mkdir(parents=True)
    # Keep a recoverable profile snapshot; existing workflow files are read, not overwritten.
    shutil.copy2(PROFILE_FILE, pack / 'previous_profile.json')
    reference = client.upload_image(profile['reference'], subfolder='')
    items = []
    for key, pose in profile['poses'].items():
        source = Path(pose['graph'])
        folder = pack / key; folder.mkdir()
        shutil.copy2(source, folder / 'source_api.json')
        graph = json.loads(source.read_text('utf-8'))
        graph['8']['inputs']['image'] = reference
        graph['21']['inputs']['image'] = client.upload_image(pose['image'], subfolder='')
        check_models(graph, info)
        write_json(folder / 'api_snapshot.json', graph)
        items.append({'key': key, 'folder': folder, 'graph': graph, 'source': source,
                      'source_hash': digest(source), 'title': '蓝发侧视 · ' + pose['title'] + ' / ControlNet'})
    info = client.request('/object_info')
    os.environ['AIPICTURES_BROWSER_PROFILE'] = str(DATA / 'test-browser' / uuid4().hex)
    app = create_application([])
    window = Window(); window.url.setText(args.url); window.show()
    state = {'stage': 'connect', 'index': 0, 'start': time.monotonic()}

    def exported(result):
        if not result['ok']: raise ValueError(result)
        item = items[state['index']]
        # Check every model, prompt, connection and image binding survived the frontend conversion.
        for key, node in item['graph'].items():
            actual = result['value']['graph'][key]
            assert actual['class_type'] == node['class_type'], key
            for field, value in node['inputs'].items(): assert actual['inputs'][field] == value, (key, field)
        ui = result['value']['workflow']
        write_json(item['folder'] / 'workflow_ui.json', ui)
        write_json(item['folder'] / 'original_ui.json', ui)
        report = inspect_workflow(ui, info)
        assert report['dependencies_ready'], report
        item['entry'] = {'id': item['folder'].parent.name + '_' + item['key'], 'title': item['title'],
            'ui_path': str((item['folder'] / 'workflow_ui.json').relative_to(DATA)),
            'source_path': str(item['folder'] / 'original_ui.json'),
            'source_sha256': digest(item['folder'] / 'original_ui.json'),
            'origin_api': str(item['source']), 'origin_api_sha256': item['source_hash'],
            'backend_url': args.url, 'imported_at': datetime.now().isoformat(timespec='seconds'),
            'compatibility': report, 'validation': {'editor_loaded': True, 'api_roundtrip_verified': True,
                                                   'generation_verified': False}}
        print('IMPORTED', item['key'], flush=True)
        state['index'] += 1; state['stage'] = 'next'

    def tick():
        if time.monotonic() - state['start'] > 900: raise TimeoutError(state['stage'])
        stage = state['stage']
        if stage == 'connect' and window.connected:
            window.tabs.setCurrentIndex(1); state['stage'] = 'next'
        elif stage == 'next' and window.editor.ready and not window.editor.pending:
            if state['index'] < len(items):
                item = items[state['index']]; state['stage'] = 'loading'
                window.editor.load_graph(item['graph'], item['title'])
            else:
                target = next(item for item in items if item['key'] == args.test_pose)
                queue = client.request('/queue')
                if queue['queue_running'] or queue['queue_pending']:
                    state['stage'] = 'waiting_for_idle'; state['idle_check'] = time.monotonic() + 2; return
                state['target'] = target
                state['job'] = window.queue_graph(target['graph'], {'mode': 'workflow_import_test',
                    'character_id': profile['id'], 'pose': target['key']},
                    json.loads((target['folder'] / 'workflow_ui.json').read_text('utf-8')))
                state['stage'] = 'generation'; print('GENERATING', target['key'], flush=True)
        elif stage == 'waiting_for_idle' and time.monotonic() >= state['idle_check']:
            state['idle_check'] = time.monotonic() + 2
            queue = client.request('/queue')
            if not queue['queue_running'] and not queue['queue_pending']:
                state['stage'] = 'next'
        elif stage == 'loading' and not window.editor.pending:
            state['stage'] = 'snapshot'; window.editor.snapshot(lambda result: guard(exported, result))
        elif stage == 'generation' and not window.current and not window.pending:
            job = json.loads((state['job'] / 'job.json').read_text('utf-8'))
            assert job['status'] == 'completed', job.get('error')
            assert window.pixmap.width() == 768 and window.pixmap.height() == 1024
            target = state['target']; target['entry']['validation'].update(generation_verified=True,
                job=str(state['job'].relative_to(DATA)))
            catalog = list_workflows()
            catalog.extend(item['entry'] for item in items)
            write_json(CATALOG, {'schema_version': 1, 'workflows': catalog})
            for item in items:
                assert digest(item['source']) == item['source_hash']
                profile['poses'][item['key']]['graph'] = str(item['folder'] / 'api_snapshot.json')
                profile['poses'][item['key']]['ui_graph'] = str(item['folder'] / 'workflow_ui.json')
            profile['deployment'] = {'backend_url': args.url, 'package': str(pack),
                'controlnet_ready': True, 'tested_pose': target['key'], 'test_job': str(state['job'])}
            write_json(PROFILE_FILE, profile)
            window.apply_character(route='pose'); window.show_image(str(state['job'] / 'image_000.png'))
            window.timer.stop(); state['stage'] = 'capture'; state['after'] = time.monotonic() + 1
            write_json(DATA / 'controlnet-import-acceptance.json', {'passed': True, 'package': str(pack),
                'imported': [item['entry']['id'] for item in items], 'tested_pose': target['key'],
                'job': str(state['job']), 'output': str(state['job'] / 'image_000.png'),
                'source_files_unchanged': True, 'backend_url': args.url})
            print('GENERATION PASSED', state['job'], flush=True)
        elif stage == 'capture' and time.monotonic() > state['after'] and not window.workers:
            window.grab().save(str(DATA / 'controlnet-import.png')); app.quit()

    def guard(fn, *values):
        try: fn(*values)
        except Exception as exc:
            print('FAILED', repr(exc), flush=True); window.timer.stop(); app.exit(1)

    timer = QTimer(); timer.timeout.connect(lambda: guard(tick)); timer.start(350)
    return app.exec()


if __name__ == '__main__': sys.exit(main())
