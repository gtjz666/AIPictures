"""Opt-in, serial real inference checks. A saved receipt is resumed, never reposted."""
import argparse
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.storage import write_json
from aipictures.workflow import ImageRequest

CASES = {
    'anime': ('一位成年女性冒险者，二维日系动漫插画，正面全身，紫色短发，蓝色夹克，黑色长裤，棕色靴子。自然站立，双臂自然下垂，双手清楚可见。干净轮廓，平涂配色，浅灰色背景。', 832, 1216),
    'portrait': ('一位成年女性的写实摄影肖像，正面面对镜头，五官比例自然，清晰的眼睛，柔和棚拍光线，纯灰色背景。', 832, 1216),
    'prop': ('单个游戏道具，装有红色药水的小玻璃瓶，软木塞，等距视角，物件居中，轮廓清楚，手绘阴影，纯浅灰色背景。', 1024, 1024),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--route', choices=['native', 'translated'], default='native')
    parser.add_argument('--case', choices=list(CASES), action='append')
    args = parser.parse_args()
    client = ComfyClient()
    info = client.discover()
    for case in args.case or list(CASES):
        folder = args.output / case
        folder.mkdir(parents=True, exist_ok=True)
        if (folder / 'result.json').exists():
            print(case, 'already complete; skipped', flush=True)
            continue
        receipt = folder / 'submission.json'
        saved = json.loads(receipt.read_text('utf-8')) if receipt.exists() else {}
        if receipt.exists() and not saved.get('prompt_id'):
            raise RuntimeError('Submission uncertain; inspect the saved receipt, do not retry.')
        queue = client.request('/queue')
        if any(row[1]!=saved.get('prompt_id') for key in ('queue_running','queue_pending') for row in queue.get(key,[])):
            raise RuntimeError('Shared backend busy; no new task submitted.')
        positive, width, height = CASES[case]
        negative = '五官模糊，多余肢体，肢体融合，水印，文字'
        request = ImageRequest('', positive, negative, width, height, 9, 1., 907012, 'euler', 'simple')
        if receipt.exists():
            graph = json.loads((folder/'workflow.json').read_text('utf-8'))
        elif args.route == 'native':
            from aipictures.zimage import build
            graph, mapping = build(request, info['object_info'])
        else:
            from aipictures.workflow import build_workflow
            from aipictures.local_translation import settings, translate
            from aipictures.storage import DATA
            translated = translate(positive, negative, settings(DATA), threading.Event())
            write_json(folder / 'translation.json', dict(translated, original_positive=positive, original_negative=negative))
            request.positive, request.negative = translated['positive'], translated['negative']
            request.checkpoint = next(name for name in info['checkpoints'] if 'Juggernaut-XL_v9_' in name)
            request.steps, request.cfg, request.sampler, request.scheduler = 30, 5.5, 'dpmpp_2m', 'karras'
            graph = build_workflow(request)
        if not receipt.exists():
            write_json(folder / 'workflow.json', graph)
            write_json(folder / 'params.json', dict(asdict(request), user_prompt=positive, route=args.route))
        def emit(kind, data):
            if kind in ('queued', 'executing', 'progress', 'condition_stage'):
                print(case, kind, json.dumps(data, ensure_ascii=False), flush=True)
        started = time.monotonic()
        if receipt.exists():
            result = client.resume(saved['prompt_id'], graph, folder, emit, threading.Event())
        else:
            result = client.generate(graph, folder, emit, threading.Event())
        result.update(seconds=round(time.monotonic()-started, 2), real_inference=True,
                      visual_acceptance='requires_review')
        write_json(folder / 'result.json', result)
        release_idle_models(client)
        print(case, 'COMPLETE', result['seconds'], flush=True)


if __name__ == '__main__':
    main()
