"""Copy active local ComfyUI workflows into AIPictures; never modify the source."""
import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from aipictures.engine import ComfyClient
from aipictures.storage import DATA, write_json
from aipictures.workflow_library import CATALOG, digest, inspect_workflow, list_workflows, workflow_path

TITLES = {
    '01_side_character_sdxl_ui': '01 · 侧视角色基础生图',
    '02_side_character_pose_sdxl_ui': '02 · 骨骼姿态控制',
    '03_animation_frame_sdxl_ipadapter_pose_ui': '03 · 参考角色与姿态单帧',
}


def migrate(source, asset_root=None, url='http://127.0.0.1:8188'):
    source = Path(source).resolve()
    files = sorted(source.glob('*.json'))
    if not files:
        raise ValueError('指定目录没有工作流 JSON')
    info = ComfyClient(url).request('/object_info')
    entries = list_workflows()
    imported = []
    for path in files:
        graph = json.loads(path.read_text('utf-8-sig'))
        if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list):
            continue
        checksum = digest(path)
        previous = next((e for e in entries if e.get('source_path') == str(path)
                         and e.get('source_sha256') == checksum
                         and workflow_path(e).is_file() and digest(workflow_path(e)) == checksum), None)
        if previous:
            previous['compatibility'] = inspect_workflow(graph, info)
            imported.append(previous)
            continue
        folder = DATA / 'workflows' / 'imported' / (path.stem + '_' + uuid4().hex[:8])
        folder.mkdir(parents=True)
        target = folder / path.name
        shutil.copy2(path, target)
        if digest(target) != checksum:
            raise RuntimeError('工作流副本校验失败：' + path.name)
        assets = []
        if asset_root:
            asset_root = Path(asset_root).resolve()
            for node in graph['nodes']:
                if node['type'] != 'LoadImage' or not node.get('widgets_values'):
                    continue
                name = node['widgets_values'][0]
                candidate = (asset_root / name).resolve()
                if candidate.is_relative_to(asset_root) and candidate.is_file():
                    dest = folder / 'assets' / Path(name).name
                    dest.parent.mkdir(exist_ok=True)
                    shutil.copy2(candidate, dest)
                    assets.append({'filename': name, 'path': str(dest.relative_to(DATA)), 'sha256': digest(dest)})
        entry = {'id': folder.name, 'title': TITLES.get(path.stem, path.stem),
                 'ui_path': str(target.relative_to(DATA)), 'source_path': str(path),
                 'source_sha256': checksum, 'imported_at': datetime.now().isoformat(timespec='seconds'),
                 'compatibility': inspect_workflow(graph, info), 'assets': assets,
                 'validation': {'editor_loaded': False, 'generation_verified': False}}
        entries.append(entry)
        imported.append(entry)
    write_json(CATALOG, {'schema_version': 1, 'workflows': entries})
    report = {'source': str(source), 'imported': imported,
              'note': '源文件保持不变；标准姿态图只复制到本软件本地素材目录，未替换 ComfyUI 的输入。'}
    write_json(DATA / 'migration-report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--asset-root')
    parser.add_argument('--url', default='http://127.0.0.1:8188')
    args = parser.parse_args()
    result = migrate(args.source, args.asset_root, args.url)
    for entry in result['imported']:
        print(entry['title'] + ' · ' + ('dependencies ready' if entry['compatibility']['dependencies_ready'] else 'missing dependencies'))
