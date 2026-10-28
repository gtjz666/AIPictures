"""Rebuild cached native animation transparency without submitting AI inference again."""
import argparse
import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from aipictures.storage import DATA,write_json
from aipictures.temporal_animation import finish_sequence


def rebuild(folder):
    started=time.monotonic()
    folder=Path(folder).resolve()
    if folder.parent!=(DATA/'animations').resolve() or not folder.is_dir():
        raise ValueError('请选择本软件 animations 缓存中的单个任务目录。')
    manifest=json.loads((folder/'sequence.json').read_text('utf-8'))
    if manifest.get('status')!='completed' or manifest.get('method')!='wan22_14b_temporal_generation':
        raise ValueError('仅支持已经完成的 Wan 连续动画缓存。')
    result=json.loads((folder/'video'/'result.json').read_text('utf-8'))
    for image in result['images']:
        path=Path(image).resolve()
        if path.parent!=(folder/'video').resolve() or not path.is_file():
            raise ValueError('原始连续帧缺失或不在本任务目录中。')
    staging=folder/('matting-'+uuid4().hex[:8]); staging.mkdir()
    def event(kind,data):
        if kind=='matte_progress': print(folder.name,data['value'],'/',data['max'],flush=True)
    finish_sequence(staging,result,manifest,event,threading.Event())
    # Complete every new export before replacing anything; keep the old alpha/export version.
    backup=folder/('matting-backup-'+datetime.now().strftime('%Y%m%d_%H%M%S')+'-'+uuid4().hex[:6])
    backup.mkdir()
    outputs=list(staging.iterdir())
    for output in outputs:
        previous=folder/output.name
        if previous.is_file(): shutil.copy2(previous,backup/output.name)
    write_json(staging/'matting-rebuild.json',{'backup':str(backup),'original_ai_frames_reused':True,
        'source_prompt_id':result['prompt_id'],'background':manifest['background'],
        'matte_frames':len(manifest['frames']),'elapsed_seconds':round(time.monotonic()-started,1)})
    for output in staging.iterdir(): os.replace(output,folder/output.name)
    staging.rmdir()
    print('Rebuilt:',folder,flush=True)
    return folder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folders',nargs='+')
    for folder in parser.parse_args().folders: rebuild(folder)


if __name__=='__main__': main()
