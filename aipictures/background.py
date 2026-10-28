"""Local CPU foreground segmentation; never upload user images to a service."""
import os
os.environ.setdefault('OMP_NUM_THREADS',str(min(6,os.cpu_count() or 1)))
import json
import shutil
import threading
from pathlib import Path
from PIL import Image, ImageOps
from .engine import Cancelled
from .storage import DATA

MODEL = 'isnet-general-use'
MODEL_ROOT = Path(os.environ.get('U2NET_HOME',str(DATA/'background-models')))
SETTINGS = DATA/'background-settings.json'
ALLOWED_MODELS = ('isnet-general-use','birefnet-general')
if SETTINGS.is_file():
    configured=json.loads(SETTINGS.read_text('utf-8'))
    if configured['model'] not in ALLOWED_MODELS: raise ValueError('不支持的本地去背景模型。')
    MODEL=configured['model']; MODEL_ROOT=Path(configured['root']).resolve()
_session = None
_lock = threading.Lock()


def model_file(model=None,root=None):
    # rembg 2.0.86 stores isolated models under <cache>/models/<name>/.
    model=model or MODEL; root=Path(root or MODEL_ROOT)
    if model not in ALLOWED_MODELS: raise ValueError('不支持的本地去背景模型。')
    return root/'models'/model/(model+'.onnx')


def create_session(model,root,allow_download=False):
    path=model_file(model,root)
    if not allow_download and not path.is_file():
        raise ValueError('本地去背景模型尚未安装：'+str(path))
    os.environ['U2NET_HOME']=str(Path(root).resolve())
    from rembg import new_session
    import onnxruntime as ort
    options=ort.SessionOptions()
    # Leave CPU capacity for Qt and the OS while processing 1024px BiRefNet frames.
    options.intra_op_num_threads=min(6,os.cpu_count() or 1)
    options.inter_op_num_threads=min(6,os.cpu_count() or 1)
    # Keep the fast allocator within a short batch, then destroy the session to free it.
    options.enable_cpu_mem_arena=True
    options.enable_mem_pattern=True
    return new_session(model,sess_opts=options,providers=['CPUExecutionProvider'])


def session(allow_download=False):
    global _session
    if not allow_download and not model_file().is_file():
        raise ValueError('本地去背景模型尚未安装，请运行 setup.bat，或运行 python -m tools.prepare_background')
    with _lock:
        if _session is None:
            _session = create_session(MODEL,MODEL_ROOT,allow_download)
    return _session


def release_session():
    """Free the CPU inference arena before the next large ComfyUI job."""
    global _session
    with _lock:
        _session=None


def foreground_rgba(image,cancel,anti_alias=True):
    """Straight RGBA: preserve source RGB instead of multiplying colors by alpha twice."""
    if cancel.is_set(): raise Cancelled('任务已取消')
    image=ImageOps.exif_transpose(image).convert('RGBA')
    alpha=image.getchannel('A')
    histogram=alpha.histogram()
    if sum(histogram[:16])>image.width*image.height*.01 and sum(histogram[64:])>100:
        return image.copy()  # An imported transparent sprite already has a deliberate matte.
    from rembg import remove
    alpha=remove(image.convert('RGB'),session=session(),only_mask=True).convert('L')
    alpha=alpha.point(lambda a:0 if a<12 else 255 if a>232 else a)
    output=image.copy()
    output.putalpha(alpha)
    if anti_alias:
        from .image_quality import smooth_alpha
        output=smooth_alpha(output)
    if cancel.is_set(): raise Cancelled('任务已取消，原图已保留')
    return output


def remove_background(path,cancel,anti_alias=True):
    with Image.open(path) as image: return foreground_rgba(image,cancel,anti_alias)


def process_result(result,folder,emit,cancel,anti_alias=True):
    try:
        session()
        originals=[]
        for i,path in enumerate(result['images']):
            emit('postprocess',{'index':i,'count':len(result['images'])})
            raw=Path(folder)/f'original_{i:03d}.png'
            if raw.exists(): raise ValueError('原始图片备份已存在，拒绝覆盖：'+str(raw))
            shutil.copy2(path,raw); originals.append(str(raw))
            cutout=remove_background(path,cancel,anti_alias); cutout.save(path)
        result['original_images']=originals
        result['background']={'transparent':True,'model':MODEL,'device':'cpu','edge_smoothing':anti_alias}
        return result
    finally: release_session()
