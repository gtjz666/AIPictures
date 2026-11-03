"""Independent motion-clip inputs; preserve source timing, never blend frames."""
import math
import json
from contextlib import nullcontext
import threading
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageOps

from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest

EXTENSIONS = {'.mp4', '.mkv', '.mov', '.webm', '.avi', '.gif'}


def sequence(path: Path) -> tuple[dict,list[Path]]:
    path=Path(path).resolve(strict=True)
    if path.stat().st_size>1_000_000:raise ValueError('动作帧清单过大。')
    data=json.loads(path.read_text('utf-8'))
    if data.get('kind')!='motion_frames' or data.get('schema_version')!=1:raise ValueError('不是动作帧序列清单。')
    fps=data.get('fps');rows=data.get('frames',[])
    if not isinstance(rows,list) or not isinstance(fps,(float,int)) or not math.isfinite(fps) or not 1<=fps<=120 or not 2<=len(rows)<=1500:
        raise ValueError('动作序列需要2–1500帧，帧率为1–120。')
    paths=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('image'),str) or not isinstance(row.get('sha256'),str):
            raise ValueError('动作帧清单缺少图片路径或校验值，请重新导入。')
        relative=Path(row['image'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('动作帧必须使用素材目录内的相对路径。')
        file=(path.parent/relative).resolve(strict=True)
        if not file.is_relative_to(path.parent):raise ValueError('动作帧路径超出素材目录。')
        if file.suffix.lower()!='.png':raise ValueError('动作序列使用PNG帧。')
        paths.append(file)
    return data,paths


def inspect(path: Path, cancel: threading.Event | None=None) -> dict:
    if cancel and cancel.is_set():raise Cancelled('动作参考准备已取消。')
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() not in EXTENSIONS|{'.json'} or not 0 < path.stat().st_size <= 2 * 1024**3:
        raise ValueError('请选择不超过2GB的MP4、GIF或其他支持的视频文件。')
    if path.suffix.lower()=='.json':
        data,paths=sequence(path)
        width=height=0;total_bytes=0
        for i,file in enumerate(paths):
            if cancel and cancel.is_set():raise Cancelled('动作参考准备已取消。')
            total_bytes+=file.stat().st_size
            if file.stat().st_size>128*1024**2 or total_bytes>2*1024**3:raise ValueError('动作帧过大：单张上限128MB，整组上限2GB。')
            with Image.open(file) as im:
                if im.format!='PNG' or im.width*im.height>8_500_000:raise ValueError('动作帧需要4K以内的有效PNG。')
                if not i:width,height=im.size
                elif im.size!=(width,height):raise ValueError('动作帧尺寸应一致，请先统一画布。')
            if digest(file)!=data['frames'][i]['sha256']:raise ValueError('动作序列中的图片已被修改。')
        count=len(paths);duration=count/data['fps']
    elif path.suffix.lower() == '.gif':
        with Image.open(path) as im:
            width, height = im.size
            if not 2 <= getattr(im, 'n_frames', 1) <= 1500:
                raise ValueError('动作GIF需要2–1500帧；静态图片请放在角色参考图。')
            duration = 0.
            for i in range(im.n_frames):
                if cancel and cancel.is_set():raise Cancelled('动作参考准备已取消。')
                im.seek(i);duration += max(10, im.info.get('duration', 100)) / 1000.
            count = im.n_frames
    else:
        with av.open(str(path)) as container:
            if not container.streams.video: raise ValueError('文件中没有视频画面。')
            s = container.streams.video[0];width, height = s.width, s.height
            duration = float(s.duration * s.time_base) if s.duration and s.time_base else (container.duration or 0) / 1e6
            count = s.frames
    if not math.isfinite(duration) or not .08 <= duration <= 120:
        raise ValueError('请选择0.08–120秒的动作片段；较长视频请先裁剪。')
    if not 1 <= width * height <= 8_500_000:
        raise ValueError('动作参考尺寸过大，请先缩小到4K以内。')
    return dict(path=str(path), width=width, height=height, duration=duration,
                frame_count=count, bytes=path.stat().st_size, sha256=digest(path))


def frames(path: Path, cancel: threading.Event):
    """Yield presentation timestamps and composited RGB; GIF disposal is handled by Pillow."""
    if path.suffix.lower()=='.json':
        data,paths=sequence(path)
        for i,file in enumerate(paths):
            if cancel.is_set():raise Cancelled('动作参考准备已取消。')
            with Image.open(file) as im:
                rgba=ImageOps.exif_transpose(im).convert('RGBA');rgb=Image.new('RGB',rgba.size,(232,232,232))
                rgb.paste(rgba,mask=rgba.getchannel('A'))
            yield i/data['fps'],rgb
    elif path.suffix.lower() == '.gif':
        with Image.open(path) as im:
            timestamp = 0.
            for i in range(im.n_frames):
                if cancel.is_set(): raise Cancelled('动作参考准备已取消。')
                im.seek(i)
                rgba = im.convert('RGBA');rgb = Image.new('RGB', rgba.size, (232, 232, 232))
                rgb.paste(rgba, mask=rgba.getchannel('A'))
                yield timestamp, rgb
                timestamp += max(10, im.info.get('duration', 100)) / 1000.
    else:
        with av.open(str(path)) as container:
            s = container.streams.video[0];s.codec_context.thread_count = 2
            origin = None;previous = -1.;fps = float(s.average_rate or 24)
            for i, frame in enumerate(container.decode(s)):
                if cancel.is_set(): raise Cancelled('动作参考准备已取消。')
                t = float(frame.time) if frame.time is not None else i / fps
                if origin is None: origin = t
                t -= origin
                if t < previous: raise ValueError('视频时间戳倒退，请先重新编码该片段。')
                previous = t
                yield t, frame.to_image().convert('RGB')


def prepare(path: Path, folder: Path, seconds: float, start: float,
            cancel: threading.Event, emit=lambda *_: None, *, max_side: int=1024, align_h3: bool=False, repeat: bool=False,
            encode_video: bool=True, save_frames: bool=False) -> dict:
    """Stream a bounded, silent 24fps nearest-time guide; no optical flow or frame mixing."""
    meta = inspect(path,cancel)
    if not all(math.isfinite(v) for v in (start, seconds)) or start < 0 or not 1 <= seconds <= 15:
        raise ValueError('动作起点应为非负数，片段时长应为1–15秒。')
    used = seconds if repeat else min(seconds, meta['duration'] - start)
    if start>=meta['duration']:raise ValueError('动作起点超出片段，请重新选择起点。')
    if not encode_video and not save_frames:raise ValueError('至少需要输出PNG帧或参考视频。')
    if used < (.08 if meta['duration']<.95 else .95): raise ValueError('所选动作区间不足，请提前起点或换一个片段。')
    source_count = math.floor(used * 24 + 1e-6)
    count = max(22,source_count + (5-source_count)%17) if align_h3 else source_count
    if max_side not in (256,512,768,1024):raise ValueError('动作参考编码边长应为256、512、768或1024。')
    if folder.exists(): raise ValueError('动作参考目录已有记录，不覆盖或重复准备。')
    folder.mkdir(parents=True)
    target = folder/'guide.mp4';partial = folder/'guide.part.mp4'
    previews = folder/'preview';previews.mkdir()
    full_frames=folder/'frames'
    if save_frames:full_frames.mkdir()
    frame_rows=[]
    width, height = meta['width'], meta['height']
    scale = min(1., max_side / max(width, height))
    width, height = max(2, round(width * scale)), max(2, round(height * scale))
    times = [start + (i if repeat else min(i,source_count-1)) / 24. for i in range(count)]
    written = 0;thumbs = []
    with av.open(str(partial), 'w') if encode_video else nullcontext(None) as container:
        stream=None
        if container:
            stream = container.add_stream('libx264rgb', rate=24)
            stream.thread_count=2
            stream.width, stream.height = width, height;stream.pix_fmt = 'rgb24'
            stream.options = {'crf':'0', 'preset':'fast'}
        def save(im):
            nonlocal written
            if cancel.is_set(): raise Cancelled('动作参考准备已取消，原文件保留。')
            if im.size != (width, height):im = im.resize((width, height), Image.Resampling.LANCZOS)
            if stream:
                vf = av.VideoFrame.from_ndarray(np.asarray(im), format='rgb24')
                for packet in stream.encode(vf):container.mux(packet)
            if save_frames:
                full=full_frames/f'frame_{written:04d}.png';im.save(full)
                frame_rows.append(dict(image=full.relative_to(folder).as_posix(),sha256=digest(full)))
            thumb = ImageOps.contain(im, (240, 180))
            p = previews/f'frame_{written:04d}.png';thumb.save(p);thumbs.append(str(p.resolve()))
            written += 1
            if written % 24 == 0:emit('video_stage', {'message':f'准备动作参考 · {written}/{count}帧'})
        previous = None;previous_time = 0.
        def timeline():
            for cycle in range(math.ceil((start+count/24.)/meta['duration']) if repeat else 1):
                for t,im in frames(Path(path),cancel):yield t+cycle*meta['duration'],im
        for t, im in timeline():
            if previous is not None:
                # A presentation timestamp marks the START of a held frame,
                # particularly for GIFs with different delays on every frame.
                while written < count and times[written] < t - 1e-9:save(previous)
            previous, previous_time = im, t
            if written == count:break
        if previous is None:raise ValueError('动作参考没有可解码的画面。')
        while written < count:save(previous)
        if stream:
            for packet in stream.encode():container.mux(packet)
    if digest(Path(path)) != meta['sha256']: raise ValueError('准备期间动作参考被修改，停止生成。')
    if encode_video:partial.replace(target)
    if save_frames:
        manifest=folder/'frames.json'
        write_json(manifest,dict(schema_version=1,kind='motion_frames',fps=24,frames=frame_rows))
        if not encode_video:target=manifest
    report = dict(source=meta, path=str(target.resolve()), sha256=digest(target),
                  start_seconds=start, used_seconds=source_count/24., encoded_seconds=count/24., requested_seconds=seconds,
                  last_frame_padding=0 if repeat else count-source_count,alignment_extension=count-source_count,max_side=max_side,
                  frames=count, fps=24, width=width, height=height, preview_frames=thumbs,
                  audio=False, temporal_blending=False, role='motion_only',repeat=repeat)
    write_json(folder/'motion.json', report)
    return report


def prompt(text: str, has_image: bool) -> str:
    """Keep user text verbatim; freeze an explicit division of reference roles."""
    subject = ('The subject identity, clothing, proportions, colors and visual style come from <Picture 1>. '
               'Transfer the movement to this subject; do not copy the performer or clothing in the motion guide.' if has_image else
               'The subject appearance and visual style are defined by the user description below.')
    return ('subject_definitions:\n<Subject 1>: '+subject+'\n<Video 1>: A silent motion guide. '
            'Follow its sequence of poses, movement direction and timing.\n'
            'summary:\n[reference generation] Animate <Subject 1> with the movement in <Video 1>.\n'
            'retention_analysis:\nKeep the subject appearance separate from the guide. '
            'Use the guide for body movement and timing only, not its performer, background or colors.\n'
            'detailed_description:\nUser requirements (preserved verbatim):\n'+text.strip()+'\n'
            'Perform the movement continuously in the order shown by the guide. Keep the complete subject in view, '
            'stable colors and details, without cuts or sudden zoom.\n'
            'overall_soundscape:\nNo source audio is transferred.\nnon_diegetic_music:\nNone.')
