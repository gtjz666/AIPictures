"""Dedicated Ref2VA source-video parts with numbered pictures and original AV clocks."""
import json
from pathlib import Path
import numpy as np
from .engine import Cancelled


def generate(folder,params,cancel,emit):
    if params['seconds']<=8:
        from .motion_native_backend import generate as single
        result=single(folder,params,cancel,emit)
        result['backend']='H3/dedicated-Ref2VA-video-edit';return result
    from .video_chain import generate as chain
    folder=Path(folder);result=chain(folder,params,cancel,emit)
    state=json.loads((folder/'chain.json').read_text('utf-8'))
    count=round(params['seconds']*32000);sound=np.zeros((2,count),np.float32);cursor=0
    for part in sorted(state['parts'],key=lambda row:row['index']):
        if cancel.is_set():raise Cancelled('视频编辑声音合并已取消。')
        directory=folder/part['folder'];path=directory/'animation.artifacts/audio.npy'
        if not path.is_file():raise ValueError('参考视频编辑片段缺少原生音轨，未用其他声音替代。')
        audio=np.load(path,allow_pickle=False)
        if audio.ndim!=2 or audio.shape[0]!=2 or not np.isfinite(audio).all():raise ValueError('片段原生音轨无效。')
        start=round(part.get('dropped_guide_frames',0)*32000/24)
        wanted=round(len(part['frames'])*32000/24);piece=audio[:,start:start+wanted]
        if piece.shape[1]<wanted:piece=np.pad(piece,((0,0),(0,wanted-piece.shape[1])))
        if cursor+wanted>count:raise ValueError('片段声音超过交付时长。')
        sound[:,cursor:cursor+wanted]=piece;cursor+=wanted
    if cursor!=count:raise ValueError('视频编辑的声音长度不完整。')
    target=folder/'animation.artifacts';target.mkdir(exist_ok=True);np.save(target/'audio.npy',sound,allow_pickle=False)
    result['backend']='H3/dedicated-Ref2VA-video-edit';return result
