"""Local CPU foreground segmentation; never upload user images to a service."""
import os
import shutil
import threading
from pathlib import Path
from PIL import Image
from .engine import Cancelled
from .storage import DATA

MODEL = 'isnet-general-use'
MODEL_ROOT = Path(os.environ.get('U2NET_HOME',str(DATA/'background-models')))
_session = None
_lock = threading.Lock()


def model_file():
    # rembg 2.0.86 stores isolated models under <cache>/models/<name>/.
    return MODEL_ROOT/'models'/MODEL/(MODEL+'.onnx')


def session(allow_download=False):
    global _session
    if not allow_download and not model_file().is_file():
        raise ValueError('本地去背景模型尚未安装，请运行 setup.bat，或运行 python -m tools.prepare_background')
    with _lock:
        if _session is None:
            os.environ.setdefault('U2NET_HOME',str(MODEL_ROOT))
            from rembg import new_session
            _session = new_session(MODEL,providers=['CPUExecutionProvider'])
    return _session


def remove_background(path,cancel):
    if cancel.is_set(): raise Cancelled('任务已取消')
    from rembg import remove
    with Image.open(path) as image:
        output = remove(image.convert('RGB'),session=session()).convert('RGBA')
    alpha=output.getchannel('A').point(lambda a:0 if a<16 else 255 if a>245 else a)
    output.putalpha(alpha)
    if cancel.is_set(): raise Cancelled('任务已取消，原图已保留')
    return output


def process_result(result,folder,emit,cancel):
    session()
    originals=[]
    for i,path in enumerate(result['images']):
        emit('postprocess',{'index':i,'count':len(result['images'])})
        raw=Path(folder)/f'original_{i:03d}.png'
        if raw.exists(): raise ValueError('原始图片备份已存在，拒绝覆盖：'+str(raw))
        shutil.copy2(path,raw); originals.append(str(raw))
        cutout=remove_background(path,cancel); cutout.save(path)
    result['original_images']=originals
    result['background']={'transparent':True,'model':MODEL,'device':'cpu'}
    return result
