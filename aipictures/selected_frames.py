"""Export only user-picked source frames; no keyframe guessing or temporal blending."""
import json
import math
import shutil
import threading
from pathlib import Path
from uuid import uuid4
from PIL import Image,PngImagePlugin
from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest


def read_source(manifest: Path) -> tuple[dict,list[Path]]:
    manifest=Path(manifest).resolve();data=json.loads(manifest.read_text('utf-8'))
    if data.get('status')!='completed':raise ValueError('请先等待完整动画生成完成。')
    paths=[(manifest.parent/f['image']).resolve() for f in data.get('frames',[])]
    if not paths or len(paths)>480 or any(not p.is_file() for p in paths):raise ValueError('源帧缺失或超过480张，请重新打开完整动画。')
    if not 0<float(data.get('fps',0))<=120:raise ValueError('源动画帧率无效。')
    return data,paths


def export_selection(manifest: Path,indices: list[int],folder: Path,target: Path,kind: str,
                     fps: int,columns: int,transparent: bool,loop: bool,cancel: threading.Event,emit,*,prepared=None) -> dict:
    manifest,folder,target=Path(manifest).resolve(),Path(folder).resolve(),Path(target).resolve()
    data,paths=read_source(manifest)
    indices=sorted(set(indices))
    if not indices or any(type(i) is not int or not 0<=i<len(paths) for i in indices):raise ValueError('请至少选取一帧有效图片。')
    if kind not in ('sheet','pngs') or not 1<=fps<=60 or not 1<=columns<=16:raise ValueError('导出类型、帧率或列数无效。')
    if folder.exists():raise ValueError('素材缓存目录已存在，请使用新任务。')
    if target in paths or target.is_relative_to(manifest.parent):raise ValueError('请导出到源动画目录以外的位置。')
    if kind=='sheet' and target.with_suffix('.json').exists():raise ValueError('同名JSON说明已存在，请选择新的文件名。')
    folder.mkdir(parents=True)
    seed=data.get('seed',data.get('params',{}).get('seed'))
    if not isinstance(seed,int) or seed<0:seed=None
    record={'schema_version':5,'kind':'walk','action':'custom','title':'手动选帧素材','method':'manual_video_frames',
        'status':'preparing','fps':fps,'loop':loop,'seed':seed,'frame_count':len(indices),'frames':[],
        'source_manifest':str(manifest),'source_manifest_sha256':digest(manifest),'source_indices':indices,
        'frame_sampling':'manual','temporal_blending':False,'content_scaled':False,'warnings':[],
        'intent':{'action':'custom','direction':'source'},'reused_processed_frames':[]}
    if data.get('source_video'):record['source_video']=data['source_video']
    def check():
        if cancel.is_set():raise Cancelled('选帧导出已取消，原动画与已处理素材保留。')
    def save():write_json(folder/'sequence.json',record)
    save()
    try:
        size=None
        for position,index in enumerate(indices):
            check()
            original=data['frames'][index]
            with Image.open(paths[index]) as source:
                image=source.convert('RGBA')
                if size and image.size!=size:raise ValueError('所选图片尺寸不一致，请分开导出。')
                size=image.size
                if transparent:
                    from .background import foreground_rgba
                    emit('selection_stage',{'message':f'处理所选帧 {position+1}/{len(indices)} · 透明背景…'})
                    rgb=image.convert('RGB').tobytes();reused=False
                    cached=(prepared or {}).get(index)
                    if cached and Path(cached).is_file():
                        with Image.open(cached) as previous:
                            if previous.size==image.size and previous.convert('RGB').tobytes()==rgb:
                                image=previous.convert('RGBA');reused=True;record['reused_processed_frames'].append(index)
                    if not reused:image=foreground_rgba(image,cancel,anti_alias=False)
                    if rgb!=image.convert('RGB').tobytes():raise ValueError('透明处理改变了原色，已停止导出。')
                pnginfo=PngImagePlugin.PngInfo()
                if seed is not None:pnginfo.add_text('Seed',str(seed))
                pnginfo.add_text('SourceFrame',str(original.get('source_frame',index)+1))
                pnginfo.add_text('SelectionFrame',str(index+1))
                image.save(folder/f'frame_{position:03d}.png',pnginfo=pnginfo)
            record['frames'].append({'index':position,'image':f'frame_{position:03d}.png','stage':'用户选取',
                'source_index':index,'source_frame':original.get('source_frame',index),
                'source_time':original.get('source_time',index/float(data['fps']))})
            emit('selection_progress',{'value':position+1,'max':len(indices)});save()
        check();columns=min(columns,len(indices));rows=math.ceil(len(indices)/columns)
        canvas=(columns*size[0],rows*size[1])
        # PNG sequences can be arbitrarily long; only a huge assembled preview is omitted.
        make_sheet=canvas[0]*canvas[1]<=64_000_000 and max(canvas)<=32768
        if kind=='sheet' and not make_sheet:raise ValueError('精灵图过大，请减少所选帧数，或选择导出独立PNG。')
        rects=[]
        for i,frame in enumerate(record['frames']):
            rects.append(dict(frame,rect={'x':i%columns*size[0],'y':i//columns*size[1],'w':size[0],'h':size[1]}))
        metadata={'schema_version':1,'frame_width':size[0],'frame_height':size[1],'columns':columns,'rows':rows,
            'padding':0,'fps':fps,'loop':loop,'seed':seed,'frame_count':len(indices),'frames':rects,
            'source_manifest_sha256':record['source_manifest_sha256'],'source_indices':indices,'sampling':'manual'}
        exports={'columns':columns,'rows':rows,'cell_size':list(size),'loop':loop}
        if make_sheet:
            sheet=Image.new('RGBA',canvas)
            try:
                for row in rects:
                    check()
                    with Image.open(folder/row['image']) as image:sheet.paste(image,(row['rect']['x'],row['rect']['y']))
                info=PngImagePlugin.PngInfo()
                if seed is not None:info.add_text('Seed',str(seed))
                sheet.save(folder/'sprite_sheet.png',pnginfo=info)
            finally:sheet.close()
            write_json(folder/'sprite_sheet.json',metadata);exports.update(sprite_sheet='sprite_sheet.png',metadata='sprite_sheet.json')
        check()
        if kind=='sheet':
            temporary=target.with_name(target.name+'.'+uuid4().hex+'.tmp')
            shutil.copyfile(folder/'sprite_sheet.png',temporary);temporary.replace(target)
            write_json(target.with_suffix('.json'),dict(metadata,sheet=target.name));saved=target
        else:
            # A fresh subfolder avoids overwriting any user's existing PNGs.
            saved=target/('frames_'+uuid4().hex[:10]);saved.mkdir()
            for row in record['frames']:shutil.copyfile(folder/row['image'],saved/row['image'])
            write_json(saved/'animation.json',metadata)
        record.update(status='completed',canvas=list(size),exports=exports,output=str(saved))
        save();return {'manifest':str(folder/'sequence.json'),'output':str(saved),'kind':kind,'metadata':metadata}
    except Exception as exc:
        record.update(status='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc));save();raise
    finally:
        if transparent:
            from .background import release_session
            release_session()
