import json
import os
from pathlib import Path
from datetime import datetime
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def new_job(graph, params):
    folder = DATA / 'jobs' / (datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:8])
    folder.mkdir(parents=True)
    write_json(folder / 'workflow.json', graph)
    write_json(folder / 'job.json', {'schema_version': 1, 'kind': 'image', 'status': 'created', 'params': params})
    return folder
