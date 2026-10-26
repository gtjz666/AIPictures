import json
import threading
import secrets
from aipictures.engine import ComfyClient, Cancelled
from aipictures.workflow import ImageRequest, build_workflow
from aipictures.storage import new_job, write_json, DATA

client = ComfyClient()
info = client.discover()
cancel = threading.Event()
graph = build_workflow(ImageRequest(info['checkpoints'][0], 'a red ceramic teapot on a wooden table', steps=80, seed=secrets.randbelow(2**63)))
folder = new_job(graph, {'test': 'targeted cancellation'})
events = []

def event(kind, data):
    events.append(kind)
    if kind == 'queued': write_json(folder / 'job.json', {'prompt_id': data['prompt_id'], 'status': 'queued', 'test': True})
    if kind == 'progress': cancel.set()

try:
    client.generate(graph, folder, event, cancel)
    raise AssertionError('Expected cancellation')
except Cancelled:
    write_json(folder / 'job.json', {'schema_version': 1, 'kind': 'image', 'status': 'cancelled', 'test': True})
    write_json(DATA / 'cancellation-test.json', {'cancelled': True, 'progress_seen': 'progress' in events})
    print('Targeted cancellation passed')
