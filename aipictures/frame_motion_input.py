"""PNG sequences join the same motion timeline without a source video decoder."""
import re
import threading
from pathlib import Path
from PIL import Image
from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest
from . import motion_guide


def import_frames(paths:list[Path],fps:int,folder:Path,cancel):
    if not 2<=len(paths)<=1500 or not 1<=fps<=120:raise ValueError('请选择2–1500张PNG，并设置1–120 FPS。')
    total=sum(Path(p).stat().st_size for p in paths)
    if total>2*1024**3:raise ValueError('动作帧整组上限2GB，请减少所选帧。')
    def key(path):return tuple((1,int(s)) if s.isdigit() else (0,s.casefold()) for s in re.split(r'(\d+)',Path(path).name))
    rows=[];source_map=[]
    for i,path in enumerate(sorted(paths,key=key)):
        if cancel.is_set():raise Cancelled('动作帧导入已取消。')
        if path.suffix.lower()!='.png':raise ValueError('动作帧序列只接受PNG。')
        if path.stat().st_size>128*1024**2:raise ValueError('单张动作帧上限128MB，请先缩小图片。')
        with Image.open(path) as im:
            if im.format!='PNG' or im.width*im.height>8_500_000:raise ValueError('动作帧需要4K以内的有效PNG。')
        target=folder/'frames'/f'frame_{i:04d}.png';copy_source(path,target,cancel)
        rows.append(dict(image=str(target.relative_to(folder)),sha256=digest(target)))
        source_map.append(dict(frame=i,source=path.name))
    manifest=folder/'source.json';write_json(manifest,dict(schema_version=1,kind='motion_frames',fps=fps,frames=rows))
    write_json(folder/'source-map.json',source_map)
    return manifest,motion_guide.inspect(manifest,cancel)


def freeze(source:Path,folder:Path,cancel):
    folder.mkdir(parents=True,exist_ok=False)
    if source.suffix.lower()=='.json':
        data,paths=motion_guide.sequence(source)
        for row,path in zip(data['frames'],paths):copy_source(path,folder/row['image'],cancel)
        target=folder/'source.json';copy_source(source,target,cancel)
    else:
        target=folder/('source'+source.suffix.lower());copy_source(source,target,cancel)
    return target


def copy_source(source:Path,target:Path,cancel:threading.Event):
    if target.exists():raise ValueError('素材目标已经存在，原文件保留。')
    target.parent.mkdir(parents=True,exist_ok=True)
    with source.open('rb') as src,target.open('xb') as out:
        while block:=src.read(4*1024*1024):
            if cancel.is_set():raise Cancelled('动作素材复制已取消，原文件保留。')
            out.write(block)
