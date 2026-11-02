"""Serial, persisted reference comparison; never overwrite or retry a submitted job."""
import argparse
import json
import shutil
import threading
import time
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageOps

from aipictures import flux_klein, zimage
from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.reference_input import opaque_reference
from aipictures.storage import write_json
from aipictures.workflow import ImageRequest
from aipictures.workflow_library import digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-job', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--family', choices=('flux_klein', 'zimage'), required=True)
    p.add_argument('--denoise', type=float, default=.45)
    p.add_argument('--text-only', action='store_true')
    p.add_argument('--style-reference', type=Path)
    p.add_argument('--url', default='http://127.0.0.1:8189')
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('目标已有记录，请检查原任务；不会覆盖或重新提交。')
    source = a.reference.resolve(strict=True)
    params = json.loads(a.source_job.read_text('utf-8'))['params']
    c = ComfyClient(a.url)
    q = c.request('/queue')
    if q.get('queue_running') or q.get('queue_pending'):
        raise ValueError('共享后端有任务，暂不开始测试。')
    info = c.discover()['object_info']
    module = flux_klein if a.family == 'flux_klein' else zimage
    r = ImageRequest(module.UNET, params['user_prompt'], params['user_negative'],
                     params['width'], params['height'], 4 if a.family == 'flux_klein' else 9,
                     1., params['seed'], 'euler', 'flux2' if a.family == 'flux_klein' else 'simple')
    ref_name = '' if a.text_only else '__reference__'
    graph, bindings = (module.build(r, info, ref_name,
                       style_reference='__style__' if a.style_reference else '') if a.family == 'flux_klein'
                       else module.build(r, info, ref_name, a.denoise))
    a.output.mkdir(parents=True)
    before = digest(source)
    frozen = a.output / ('reference' + source.suffix)
    shutil.copy2(source, frozen)
    with Image.open(frozen) as im:
        rgb = (zimage.prepare_reference(im, r.width, r.height) if a.family == 'zimage'
               else opaque_reference(ImageOps.exif_transpose(im).convert('RGBA')))
    prepared = a.output / 'reference_rgb.png'
    rgb.save(prepared)
    if ref_name:
        graph['reference']['inputs']['image'] = c.upload_image(prepared)
    if a.style_reference:
        with Image.open(a.style_reference) as im:
            opaque_reference(ImageOps.exif_transpose(im).convert('RGBA')).save(a.output / 'style_rgb.png')
        graph['style_reference']['inputs']['image'] = c.upload_image(a.output / 'style_rgb.png')
    params = dict(asdict(r), user_prompt=r.positive, user_negative=r.negative,
                  model_family=a.family, bindings=bindings,
                  reference=str(frozen.resolve()) if ref_name else None, reference_sha256=before if ref_name else None,
                  denoise=a.denoise if a.family == 'zimage' and ref_name else 1.,
                  reference_policy='none' if a.text_only else 'img2img' if a.family == 'zimage' else 'semantic',
                  style_reference=str(a.style_reference) if a.style_reference else None,
                  output_background='preserve', edge_smoothing=False, quality_mode='off')
    write_json(a.output / 'params.json', params)
    write_json(a.output / 'workflow.json', graph)
    write_json(a.output / 'job.json', dict(kind='image', status='running', params=params))
    release_idle_models(c)
    start = time.monotonic()
    def emit(kind, data):
        if kind in ('queued', 'executing', 'progress', 'monitor_waiting'):
            print(kind, data, flush=True)
    try:
        result = c.generate(graph, a.output, emit, threading.Event())
        result.update(elapsed_seconds=round(time.monotonic() - start, 2),
                      image_sha256=[digest(Path(f)) for f in result['images']])
        assert digest(source) == before
        write_json(a.output / 'result.json', result)
        write_json(a.output / 'job.json', dict(kind='image', status='completed', params=params))
        print('REAL_REFERENCE_PROBE_PASS', a.family, result['elapsed_seconds'], flush=True)
    except Exception as exc:
        write_json(a.output / 'job.json', dict(kind='image', status='failed', params=params, error=str(exc)))
        raise
    finally:
        release_idle_models(c)


if __name__ == '__main__':
    main()
