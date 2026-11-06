"""Full-animation preview media; sprite extraction is a separate user operation."""
from pathlib import Path
import math
import threading

import av
import numpy as np
from PIL import Image

from .engine import Cancelled


def native_rgb_info(source: Path) -> tuple[int,int,int]:
    array=np.load(source,mmap_mode='r',allow_pickle=False)
    try:
        if array.dtype!=np.uint8 or array.ndim!=4 or array.shape[-1]!=3:
            raise ValueError('原生颜色数据不是有效的uint8 RGB动画，原始文件保留。')
        count,height,width,_=array.shape
        if not 1<=count<=480 or not 1<=height*width<=8_000_000:
            raise ValueError('原生颜色数据超出当前预览限制。')
        return count,height,width
    finally:
        if hasattr(array,'_mmap'):array._mmap.close()


def native_rgb_image(source: Path,index: int) -> Image.Image:
    count,_,_=native_rgb_info(source)
    if not 0<=index<count:raise ValueError('预览帧超出动画范围。')
    array=np.load(source,mmap_mode='r',allow_pickle=False)
    try:return Image.fromarray(np.array(array[index],copy=True))
    finally:
        if hasattr(array,'_mmap'):array._mmap.close()


def encode_native_rgb(source: Path,target: Path,fps: int,cancel: threading.Event,emit,*,frame_count: int | None=None) -> None:
    """Lossless video export directly from VAE RGB; no intermediate PNG sequence."""
    count,height,width=native_rgb_info(source)
    if frame_count is not None:
        if type(frame_count) is not int or not 1<=frame_count<=count:raise ValueError('导出帧数超出原动画范围。')
        count=frame_count
    array=np.load(source,mmap_mode='r',allow_pickle=False)
    temporary=target.with_name(target.stem+'.part'+target.suffix)
    try:
        with av.open(str(temporary),'w') as container:
            stream=container.add_stream('libx264rgb',rate=fps)
            stream.width,stream.height=width,height
            stream.pix_fmt='rgb24';stream.options={'crf':'0','preset':'fast'}
            for i in range(count):
                if cancel.is_set():raise Cancelled('视频导出已取消，原动画保留。')
                frame=av.VideoFrame.from_ndarray(np.ascontiguousarray(array[i]),format='rgb24')
                for packet in stream.encode(frame):container.mux(packet)
                emit('video_export_progress',dict(value=i+1,max=count))
            for packet in stream.encode():container.mux(packet)
        temporary.replace(target)
    finally:
        if hasattr(array,'_mmap'):array._mmap.close()


def prepare_export_frames(manifest: Path,cancel: threading.Event,emit) -> None:
    """Only materialize PNGs after the user chooses frame/sprite export."""
    import json
    from uuid import uuid4
    from .storage import write_json
    path=Path(manifest);data=json.loads(path.read_text('utf-8'))
    if data.get('frames'):return
    if not data.get('native_rgb_source'):raise ValueError('原生帧数据缺失，无法提取动画帧。')
    paths=native_rgb_frames(Path(data['native_rgb_source']),path.parent/('export_frames_'+uuid4().hex[:8]),cancel,emit,
                            frame_count=data.get('frame_count'))
    if cancel.is_set():raise Cancelled('拆帧已取消，原动画保留。')
    data['frames']=[dict(image=str(p.relative_to(path.parent))) for p in paths]
    data['frame_storage']='png';write_json(path,data)


def encode_pngs(paths: list[Path], target: Path, fps: int, cancel: threading.Event) -> None:
    if not paths:raise ValueError('没有可保存的完整动画帧。')
    with Image.open(paths[0]) as first:width,height=first.size
    temporary=target.with_name(target.stem+'.part'+target.suffix)
    with av.open(str(temporary),'w') as container:
        stream=container.add_stream('libx264rgb',rate=fps)
        stream.width,stream.height=width,height
        stream.pix_fmt='rgb24';stream.options={'crf':'0','preset':'fast'}
        for path in paths:
            if cancel.is_set():raise Cancelled('已取消视频保存，原始帧保留。')
            with Image.open(path) as source:
                if source.size!=(width,height):raise ValueError('源帧画布不一致，原始帧保留。')
                frame=av.VideoFrame.from_ndarray(np.asarray(source.convert('RGB')),format='rgb24')
            for packet in stream.encode(frame):container.mux(packet)
        for packet in stream.encode():container.mux(packet)
    temporary.replace(target)


def preview_frames(source: Path, folder: Path, cancel: threading.Event, emit) -> tuple[list[Path],float]:
    folder.mkdir(parents=True,exist_ok=False);paths=[]
    with av.open(str(source)) as container:
        if not container.streams.video:raise ValueError('文件中没有可预览的动画画面。')
        stream=container.streams.video[0];fps=float(stream.average_rate or 24)
        if not 1<=fps<=120 or stream.width*stream.height>8_000_000:
            raise ValueError('动画尺寸或帧率超出预览范围，请先裁剪。')
        for i,frame in enumerate(container.decode(stream)):
            if cancel.is_set():raise Cancelled('已取消预览准备，原视频保留。')
            if i>=math.ceil(7200*fps):raise ValueError('动画超过2小时，请先裁剪再预览。')
            path=folder/f'frame_{i:04d}.png'
            Image.fromarray(frame.to_ndarray(format='rgba')).save(path);paths.append(path)
            if i%12==0:emit('video_stage',{'message':f'准备完整动画预览 · {i+1} 帧'})
    if not paths:raise ValueError('视频没有可解码的动画画面。')
    return paths,fps


def native_rgb_frames(source: Path,folder: Path,cancel: threading.Event,emit,*,frame_count: int | None=None) -> list[Path]:
    """Prefer H3's exact VAE RGB artifact to a chroma-subsampled delivery MP4."""
    array=np.load(source,mmap_mode='r',allow_pickle=False)
    try:
        if array.dtype!=np.uint8 or array.ndim!=4 or array.shape[-1]!=3:
            raise ValueError('原生颜色数据不是有效的uint8 RGB动画，原始文件保留。')
        count,height,width,_=array.shape
        if not 1<=count<=480 or not 1<=height*width<=8_000_000:
            raise ValueError('原生颜色数据超出当前预览限制。')
        if frame_count is not None:
            if type(frame_count) is not int or not 1<=frame_count<=count:raise ValueError('导出帧数超出原动画范围。')
            count=frame_count
        folder.mkdir(parents=True,exist_ok=False);paths=[]
        for i in range(count):
            if cancel.is_set():raise Cancelled('预览准备已取消，原生颜色数据保留。')
            path=folder/f'frame_{i:04d}.png';Image.fromarray(array[i]).save(path);paths.append(path)
            if i%12==0:emit('video_stage',{'message':f'保存原生RGB动画 · {i+1}/{count} 帧'})
        return paths
    finally:
        if hasattr(array,'_mmap'):array._mmap.close()
