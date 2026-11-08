"""Explicit offline SDPose audit on frozen single-actor diagnostic frames.

Run in the existing private Comfy Python. No server, generation, or UI changes.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from tools.probe_pose_control import BODY_NAMES, digest, draw_overlay, rgba_rgb, source_samples

MODEL_SHA = '63d01f9a7494560693b24767f4469d59c9d3266b31ff0a253e74d1e611442721'
COCO_FROM_OPENPOSE = [0, 15, 14, 17, 16, 5, 2, 6, 3, 7, 4, 11, 8, 12, 9, 13, 10]


def check_backends(urls):
    """Read queues only. No desktop-client dependency in the private environment."""
    from urllib.request import urlopen
    from urllib.error import URLError
    from urllib.parse import urlparse
    records = []
    for url in dict.fromkeys(urls):
        parsed = urlparse(url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
            raise ValueError('Diagnostic queue checks require local HTTP URLs')
        try:
            with urlopen(url.rstrip('/')+'/queue', timeout=3) as response:
                queue = json.load(response)
        except URLError as exc:
            if isinstance(exc.reason, ConnectionRefusedError):
                records.append(dict(url=url, status='offline'))
                continue
            raise RuntimeError('Cannot confirm backend is idle: '+url) from exc
        if not isinstance(queue, dict) or any(not isinstance(queue.get(k), list)
                                             for k in ('queue_running', 'queue_pending')):
            raise ValueError('Invalid queue response: '+url)
        if queue['queue_running'] or queue['queue_pending']:
            raise ValueError('Another backend job is running; diagnostic not started')
        records.append(dict(url=url, status='idle'))
    return records


def run(args):
    if args.folder.exists():
        raise ValueError('Refusing to overwrite an existing probe directory')
    if digest(args.model) != MODEL_SHA:
        raise ValueError('SDPose checksum differs from publisher')
    args.folder.mkdir(parents=True)
    def state(status, stage, progress=0):
        row = dict(pid=os.getpid(), state=status, stage=stage, progress=progress,
                   folder=str(args.folder.resolve()), maximum=len(args.seconds)+1,
                   queued_count=0, updated_at=time.time(), device=args.device)
        (args.folder/'probe-state.json').write_text(json.dumps(row), encoding='utf-8')
        if owns_context:
            # A GUI may start after this CLI. Recheck ownership on every write.
            current = read_json(context_path)
            if not current or current.get('pid') == os.getpid() or process_alive(current.get('pid')) is False:
                from aipictures.storage import write_json
                write_json(context_path, row, durable=True)
    context_path = args.watch_data/'gpu-watch-context.json' if args.watch_data else None
    owns_context = False
    if context_path:
        from aipictures.gpu_watch import read_json, process_alive
        previous = read_json(context_path)
        owns_context = not previous or process_alive(previous.get('pid')) is False
    state('running', '姿态结构验证：启动')
    if args.device == 'cuda':
        records = check_backends(args.backend_url or ['http://127.0.0.1:8188', 'http://127.0.0.1:8189'])
        (args.folder/'queue-preflight.json').write_text(json.dumps(records), encoding='utf-8')
    # Parse official Comfy flags before importing any Comfy/Torch module.
    # This does not modify the private environment or shared Comfy process.
    sys.path.insert(0, str(args.comfy.resolve()))
    sys.argv = ['pose-input-audit', '--use-pytorch-cross-attention']
    if args.device == 'cpu':
        sys.argv.append('--cpu')
    import comfy.options
    comfy.options.enable_args_parsing()
    import torch
    import numpy as np
    from PIL import Image, ImageDraw, ImageOps
    torch.set_num_threads(4)
    import comfy.sd
    import comfy.sample
    import comfy.model_management as mm
    from comfy_extras.nodes_sdpose import SDPoseKeypointExtractor
    if mm.get_torch_device().type != args.device:
        raise ValueError('Actual device differs from explicitly selected diagnostic device')
    print(f'Loading official SDPose on {args.device}; no H3 model', flush=True)
    model, _, vae, _ = comfy.sd.load_checkpoint_guess_config(str(args.model), output_clip=False)
    samples, source_meta = source_samples(args.source, args.seconds)
    with Image.open(args.target) as image:
        samples.append(('target appearance (not source motion)', rgba_rgb(image), dict(target=True)))
    rows, cards = [], []
    with torch.inference_mode():
        for i, (label, image, meta) in enumerate(samples):
            started = time.perf_counter()
            print('Extracting '+label, flush=True)
            state('running', '姿态结构验证：'+label, i)
            tensor = torch.from_numpy(np.array(image).astype(np.float32) / 255)[None]
            frame = SDPoseKeypointExtractor.execute(model, vae, tensor, batch_size=1).result[0][0]
            if len(frame['people']) != 1:
                raise ValueError('Expected one person in full-image diagnostic')
            raw = np.array(frame['people'][0]['pose_keypoints_2d']).reshape(18, 3)
            body = raw[COCO_FROM_OPENPOSE]
            p, s = body[:, :2], body[:, 2]
            seconds = time.perf_counter() - started
            row = dict(label=label, **meta, size=list(image.size), elapsed=seconds,
                       openpose=frame, body_coco=body.tolist(),
                       visible_limb_joints=int(sum(s[5:17] >= .3)),
                       limb_confidence={BODY_NAMES[j]: float(s[j]) for j in range(5, 17)})
            (args.folder / f'{i:02d}-pose.json').write_text(json.dumps(row, indent=2), encoding='utf-8')
            image.save(args.folder / f'{i:02d}-original.png')
            overlay = draw_overlay(image, p, s)
            overlay.save(args.folder / f'{i:02d}-overlay.png')
            rows.append(row)
            print(json.dumps(dict(label=label, elapsed=seconds,
                                  visible_limb_joints=row['visible_limb_joints'])), flush=True)
            card = Image.new('RGB', (500, 420), 'white')
            for x, im in ((0, image), (250, overlay)):
                fitted = ImageOps.contain(im, (243, 360))
                card.paste(fitted, (x+(243-fitted.width)//2, 28+(360-fitted.height)//2))
            d = ImageDraw.Draw(card)
            d.text((4, 5), label, fill='black')
            d.text((4, 392), f'limb joints >=0.3: {row["visible_limb_joints"]}/12', fill='black')
            cards.append(card)
    mm.unload_all_models()
    sheet = Image.new('RGB', (1500, ((len(cards)+2)//3)*420), '#d0d0d0')
    for i, card in enumerate(cards):
        sheet.paste(card, ((i%3)*500, (i//3)*420))
    sheet.save(args.folder / 'body-overlays.png')
    result = dict(schema=1, cpu_only=args.device == 'cpu', device=str(mm.get_torch_device()),
                  detector='none; single-actor full-image diagnostic',
                  model=dict(path=str(args.model.resolve()), sha256=MODEL_SHA),
                  comfy=dict(path=str(args.comfy.resolve()),
                             extractor_sha256=digest(args.comfy/'comfy_extras/nodes_sdpose.py')),
                  dependencies=dict(torch=torch.__version__, numpy=np.__version__),
                  source=dict(path=str(args.source.resolve()), sha256=digest(args.source), **source_meta),
                  target=dict(path=str(args.target.resolve()), sha256=digest(args.target),
                              analysis_background_rgb=[127, 127, 127]),
                  samples=rows, visual_review_required=True, input_gate_passed=None,
                  note='Scores across extractors are not calibrated accuracy. No missing joint imputation; no video generation.')
    (args.folder / 'extraction.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    state('completed', '姿态结构验证完成；未运行H3生成', len(samples))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'target', 'model', 'comfy', 'folder'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--seconds', type=float, nargs='+', default=[0, .8, 2, 4])
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu',
                        help='CUDA is opt-in; run only after checking other model tasks are idle')
    parser.add_argument('--watch-data', type=Path)
    parser.add_argument('--backend-url', action='append', help='All known local Comfy URLs, if nondefault')
    args = parser.parse_args()
    try:
        run(args)
    except BaseException as exc:
        state_path = args.folder/'probe-state.json'
        if state_path.is_file():
            row = json.loads(state_path.read_text(encoding='utf-8'))
            if row.get('pid') == os.getpid():
                row.update(state='failed', stage='姿态结构验证未完成', error=str(exc), updated_at=time.time())
                state_path.write_text(json.dumps(row), encoding='utf-8')
                if args.watch_data:
                    from aipictures.gpu_watch import read_json
                    from aipictures.storage import write_json
                    context_path = args.watch_data/'gpu-watch-context.json'
                    if read_json(context_path).get('pid') == os.getpid():
                        write_json(context_path, row, durable=True)
        raise


if __name__ == '__main__':
    main()
