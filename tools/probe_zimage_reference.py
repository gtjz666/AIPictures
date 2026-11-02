"""One real Z-Image img2img probe; no new weights, no overwrite or auto resubmission."""
import argparse
import threading
import time
from dataclasses import asdict
from pathlib import Path

from PIL import Image

from aipictures import zimage
from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.storage import write_json
from aipictures.workflow import ImageRequest
from aipictures.workflow_library import digest

CASES={
    'retouch': '参考图中的同一位成年女性角色，全身右侧视图，紫色盘发、绿色眼睛、白色无袖衬衫、黑色领结、黑色短裤、黑色长袜、棕黑色皮鞋。保持现有站姿、身体比例、服装与颜色，清晰细腻的日式二维动画线稿和赛璐璐平涂，浅灰背景。',
    'blue': '同一位成年女性角色，全身右侧视图，紫色盘发、绿色眼睛，穿天蓝色无袖衬衫、黑色领结、黑色短裤、黑色长袜、棕黑色皮鞋，双手自然下垂。将参考图白色上衣改为天蓝色，保持其余服装、发型、站姿、配色与身体比例。日式二维动画风格，完整头部和双脚，浅灰背景。',
    'blue_target': '日式二维动画风格，一位成年女性角色，全身右侧视图，紫色盘发，绿色眼睛，穿着一件纯蓝色的无袖衬衫，整件衬衫全部为鲜明的天蓝色布料，黑色领结、黑色短裤、黑色长袜和棕黑色皮鞋。双手自然下垂，全身站立，保持参考图的身体比例和画风，清晰线稿和赛璐璐平涂，浅灰纯色背景，完整头部和双脚。',
    'front': '参考图中的同一位成年女性角色，改成正面全身站立，面对镜头，双手自然下垂，两脚分开。紫色盘发、绿色眼睛、白色无袖衬衫、黑色领结、黑色短裤、黑色长袜、棕黑色皮鞋，保持角色设计、原有配色与二维动画风格，完整头部和双脚，浅灰背景。',
}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--url',default='http://127.0.0.1:8189');p.add_argument('--case',choices=CASES,required=True)
    p.add_argument('--denoise',type=float,default=.45);p.add_argument('--seed',type=int,default=20261102)
    a=p.parse_args()
    if a.output.exists():raise ValueError('目标已有记录，请先检查；不会覆盖或重复生成。')
    if not a.reference.is_file():raise ValueError('参考图不存在。')
    c=ComfyClient(a.url);q=c.request('/queue')
    if q.get('queue_running') or q.get('queue_pending'):raise ValueError('共享后端有任务，暂不开始测试。')
    info=c.discover()['object_info'];r=ImageRequest(zimage.UNET,CASES[a.case],'多余肢体，重影，水印，模糊',768,1024,9,1.,a.seed,'euler','simple')
    graph,mapping=zimage.build(r,info,'__reference__',a.denoise)
    a.output.mkdir(parents=True)
    import shutil
    frozen=a.output/('reference'+a.reference.suffix.lower());shutil.copy2(a.reference,frozen)
    original=digest(a.reference)
    with Image.open(frozen) as source:zimage.prepare_reference(source,r.width,r.height).save(a.output/'reference_rgb.png')
    graph['reference']['inputs']['image']=c.upload_image(a.output/'reference_rgb.png')
    params={**asdict(r),'mode':'chat','model_family':'zimage','user_prompt':r.positive,'user_negative':r.negative,
        'bindings':mapping,'denoise':a.denoise,'reference':str(frozen.resolve()),'reference_sha256':original,
        'reference_policy':'img2img','reference_preprocessing':'contain_pad_rgb','output_background':'preserve',
        'quality_mode':'off','edge_smoothing':False,'matting_before_generation':False,'translation':False}
    write_json(a.output/'params.json',params);write_json(a.output/'workflow.json',graph)
    write_json(a.output/'job.json',{'schema_version':1,'kind':'image','status':'running','params':params})
    release_idle_models(c);started=time.monotonic()
    def emit(kind,data):
        if kind in ('queued','executing','progress','monitor_waiting'):print(kind,data,flush=True)
    try:
        result=c.generate(graph,a.output,emit,threading.Event())
        result.update(elapsed_seconds=round(time.monotonic()-started,2),image_sha256=[digest(Path(f)) for f in result['images']])
        write_json(a.output/'result.json',result)
        assert digest(a.reference)==original
        write_json(a.output/'job.json',{'schema_version':1,'kind':'image','status':'completed','params':params})
        print('REAL_ZIMAGE_REFERENCE_PASS',result['elapsed_seconds'],flush=True)
    except Exception as exc:
        write_json(a.output/'job.json',{'schema_version':1,'kind':'image','status':'failed','params':params,'error':str(exc)})
        raise
    finally:release_idle_models(c)


if __name__=='__main__':main()
