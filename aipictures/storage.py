import json
import os
import time
from pathlib import Path
from datetime import datetime
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'


def write_json(path, value, *, durable: bool = False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        with temp.open('w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            if durable:
                # Atomic replacement protects readers; flushing first also keeps
                # critical task records out of the OS write cache before rename.
                output.flush()
                os.fsync(output.fileno())
        # Windows readers/virus scanners can briefly deny delete-sharing on the
        # destination. Preserve the old valid JSON and retry the same atomic
        # replacement; a transient lock must not lose a running GPU task.
        for attempt in range(7):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt==6:raise
                time.sleep(min(.02*2**attempt,.32))
    finally:
        try:temp.unlink(missing_ok=True)
        except OSError:pass  # A cleanup lock must not hide the original write error.


def new_job(graph, params):
    folder = DATA / 'jobs' / (datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:8])
    folder.mkdir(parents=True)
    write_json(folder / 'workflow.json', graph)
    write_json(folder / 'job.json', {'schema_version': 1, 'kind': 'image', 'status': 'created', 'params': params})
    return folder
