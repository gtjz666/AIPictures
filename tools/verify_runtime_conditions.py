"""Real condition-only check: no diffusion model loading or animation sampling."""
import argparse
import json
import threading
import time
from pathlib import Path

from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.storage import write_json
from aipictures.temporal_animation import video_workflow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/'result.json').exists():
        print('Condition check already complete; no new task.', flush=True)
        return
    client = ComfyClient()
    queue = client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):
        raise RuntimeError('Backend busy; no new condition task submitted.')
    receipt = folder/'submission.json'
    if receipt.exists():
        graph = json.loads((folder/'workflow.json').read_text('utf-8'))
        saved = json.loads(receipt.read_text('utf-8'))
        if not saved.get('prompt_id'):
            raise RuntimeError('Uncertain receipt: inspect it rather than resubmit.')
    else:
        info = client.discover()['object_info']
        if 'AIPicturesWanImageToVideo' not in info:
            raise ValueError('Install the optional runtime nodes and refresh the backend first.')
        original = video_workflow(client.upload_image(args.reference),
            '固定镜头，同一个完整角色，先下蹲再站起，保持参考配色与服装。',
            '多余肢体，重影，变色', 907012, 20, 33, size=(768, 1024))
        graph = {key: original[key] for key in ('3', '4', '5', '6', '7', '8')}
        graph['8']['class_type'] = 'AIPicturesWanImageToVideo'
        graph['save'] = {'class_type':'SaveLatent','inputs':{
            'samples':['8',2], 'filename_prefix':'AIPictures/diagnostics/free_conditions'}}
        write_json(folder/'workflow.json', graph)
    def emit(kind, data):
        if kind in ('queued', 'executing', 'condition_stage'):
            print(kind, json.dumps(data, ensure_ascii=False), flush=True)
    started = time.monotonic()
    if receipt.exists():
        result = client.resume(saved['prompt_id'], graph, folder, emit,
                               threading.Event(), allow_latent_only=True)
    else:
        result = client.generate(graph, folder, emit, threading.Event(), allow_latent_only=True)
    result.update(seconds=round(time.monotonic()-started,2),
                  scope='condition_encode_only', diffusion_sampling_performed=False)
    write_json(folder/'result.json', result)
    release_idle_models(client)
    print('FREE_CONDITIONS_COMPLETE', result['seconds'], flush=True)


if __name__ == '__main__':
    main()
