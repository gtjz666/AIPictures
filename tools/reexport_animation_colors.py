"""Re-export an animation using verified existing alpha, without model inference."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import threading

from aipictures.animation_detail import COLOR_MODES
from aipictures.pose_animation import export_frames
from aipictures.storage import write_json


def reexport(source:Path,out:Path,mode='original'):
    source=source.resolve();out=out.resolve()
    if out.exists():raise ValueError('输出目录已存在，请选择新目录，避免覆盖已有作品。')
    if mode not in COLOR_MODES:raise ValueError('未知配色处理方式。')
    manifest=json.loads((source/'sequence.json').read_text('utf-8'))
    clip=json.loads((source/'motion.json').read_text('utf-8'))
    result=json.loads((source/'video/result.json').read_text('utf-8'))
    caches=[source/f['native_matte'] for f in manifest['frames']]
    if not caches or not all(p.is_file() for p in caches):
        raise ValueError('原生透明帧缺失，不能安全复用背景处理结果。')
    out.mkdir(parents=True);(out/'video').mkdir()
    for name in ('reference_analysis.json','motion.json'):
        if (source/name).is_file():shutil.copy2(source/name,out/name)
    shutil.copy2(source/'video/workflow.json',out/'video/workflow.json')
    result=deepcopy(result);paths=[]
    for i,path in enumerate(result['images']):
        target=out/'video'/f'image_{i:03d}.png';shutil.copy2(path,target);paths.append(str(target))
    result['images']=paths;write_json(out/'video/result.json',result)
    manifest=deepcopy(manifest);manifest.update(frames=[],status='processing',color_mode=mode,
        title='动画清晰度修订 · '+COLOR_MODES[mode],reexport_source=str(source))
    for key in ('reference_palette','color_processing','color_consistency','quality_review'):
        manifest.pop(key,None)
    write_json(out/'sequence.json',manifest)
    try:
        return export_frames(out,result,manifest,clip,lambda k,d:None,threading.Event(),matte_cache=caches)
    except Exception as exc:
        manifest.update(status='failed',error=str(exc));write_json(out/'sequence.json',manifest);raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sequence',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--mode',choices=tuple(COLOR_MODES),default='original')
    a=p.parse_args();print(json.dumps(reexport(a.sequence,a.out,a.mode),ensure_ascii=False))


if __name__=='__main__':main()
