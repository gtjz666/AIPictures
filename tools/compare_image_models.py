"""Serial, reproducible real model probes. Completed outputs are never overwritten."""
import argparse
import json
import threading
import time
from pathlib import Path

from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.storage import write_json
from aipictures.workflow import ImageRequest
from aipictures.workflow_library import digest

CASES = {
    'anime': ('日式二维动画风格，一个成年女性游戏角色，全身正面，紫色盘发，白色无袖衬衫，黑色短裤，黑色长袜和黑色皮鞋。双手自然下垂，两脚分开站立，头和鞋完整入镜。清晰线稿，平涂赛璐璐，浅灰纯色背景，只画一个人物。', 768, 1024),
    'anime_en': ('Japanese 2D animation style, one adult female game character, full body front view. Purple hair tied in an updo bun, white sleeveless blouse, black shorts, black long stockings and black leather shoes. Both hands hanging naturally at her sides, feet apart, entire head and both shoes inside the frame. Crisp line art, flat cel shading, plain light gray background, only one person.', 768, 1024),
    'portrait': ('真实摄影，一位30岁的东亚女性，黑色短发，穿深蓝色衬衫，正面半身肖像，直视镜头，左右眼清晰对称，真实皮肤细节，自然柔和窗光，灰色摄影棚背景。', 768, 1024),
    'prop': ('游戏道具概念图，一只红色药水玻璃瓶，透明玻璃，圆形瓶身，木塞封口，金属环绕瓶颈，正面三分之四视角，只画一个物件，白色干净背景，清晰轮廓和精细材质，无文字。', 1024, 1024),
    'scene': ('二维横版游戏背景，广角侧视图，日落时的森林村庄，左边一间木屋，中间一座跨过小溪的石桥，右边一棵巨大的树。前景草地，中景建筑，远景青山，手绘水彩风格，层次分明，无人物，无文字。', 1152, 768),
    'front_edit': ('将参考图中的同一位角色改为正面全身站立，面向镜头，双手自然垂在身体两侧，两脚分开。保持紫色盘发、白色无袖衬衫、黑色短裤、黑色长袜、黑色皮鞋以及原有二维动漫画风和配色。浅灰纯色背景，完整头部和双脚，只画一个人物。', 768, 1024),
}


def run(family: str, cases: list[str], output: Path, reference: Path | None = None) -> None:
    from aipictures import zimage, flux_klein
    if 'front_edit' in cases:
        if not reference or not reference.is_file():
            raise ValueError('参考编辑对照需要有效的 --reference 文件，请先检查路径。')
        if family=='zimage':raise ValueError('Z-Image Turbo 当前没有语义参考编辑能力。')
    client = ComfyClient()
    info = client.discover()['object_info']
    for name in cases:
        folder = output / (family + '_' + name)
        if folder.exists():
            raise ValueError(f'已有记录，请先检查旧任务，不会重新提交：{folder}')
        queue = client.request('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise ValueError('共享ComfyUI有其他任务；停止本轮对照，不取消其他任务。')
        prompt, width, height = CASES[name]
        if name == 'front_edit' and (not reference or not reference.is_file()):
            raise ValueError('参考编辑对照需要 --reference 文件。')
        if name == 'front_edit' and family == 'zimage':
            raise ValueError('Z-Image Turbo 当前没有语义参考编辑能力。')
        release_idle_models(client)
        folder.mkdir(parents=True)
        request = ImageRequest('unused', prompt, '', width, height, seed=20261102)
        reference_name = ''
        if name == 'front_edit':
            from PIL import Image, ImageOps
            from aipictures.reference_analysis import opaque_reference
            with Image.open(reference) as source:
                rgba=ImageOps.exif_transpose(source).convert('RGBA')
                opaque_reference(rgba).save(folder/'reference_rgb.png')
            reference_name=client.upload_image(folder/'reference_rgb.png')
        graph, _ = (flux_klein.build(request, info, reference_name) if family == 'flux_klein'
                    else zimage.build(request, info))
        write_json(folder / 'workflow.json', graph)
        params = {'model_family': family, 'prompt': prompt, 'seed': request.seed,
                  'width': width, 'height': height, 'reference': str(reference) if reference_name else None,
                  'reference_sha256': digest(reference) if reference_name else None,
                  'steps': 4 if family == 'flux_klein' else 9, 'cfg': 1.,
                  'translation': False, 'matting_before_generation': False}
        write_json(folder / 'params.json', params)
        started = time.monotonic()
        def emit(kind, data):
            if kind in ('queued', 'executing', 'progress', 'monitor_waiting'):
                print(name, kind, json.dumps(data, ensure_ascii=False), flush=True)
        try:
            result = client.generate(graph, folder, emit, threading.Event())
            result.update(params=params, elapsed_seconds=round(time.monotonic() - started, 2),
                          image_sha256=[digest(Path(p)) for p in result['images']])
            write_json(folder / 'result.json', result)
            print('COMPLETE', family, name, result['elapsed_seconds'], flush=True)
        except Exception as exc:
            write_json(folder / 'probe-error.json', {'error': str(exc), 'params': params})
            raise
    release_idle_models(client)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--family', choices=('zimage', 'flux_klein'), required=True)
    p.add_argument('--case', choices=CASES, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reference', type=Path)
    a = p.parse_args()
    run(a.family, a.case, a.output, a.reference)


if __name__ == '__main__':
    main()
