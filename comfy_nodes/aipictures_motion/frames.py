"""Verified PNG batch input for native H3."""
import hashlib
import json
from pathlib import Path
import folder_paths
import numpy as np
import torch
from PIL import Image


class AIPicturesMotionFrames:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'manifest':('STRING',{'default':'motion/frames.json'})}}
    RETURN_TYPES=('IMAGE',)
    FUNCTION='load'
    CATEGORY='AIPictures/motion'

    def load(self,manifest):
        root=Path(folder_paths.get_input_directory()).resolve()
        source=(root/manifest).resolve(strict=True)
        if not source.is_relative_to(root) or source.suffix.lower()!='.json' or source.stat().st_size>1_000_000:
            raise ValueError('动作帧清单不在本次输入目录中。')
        data=json.loads(source.read_text('utf-8'));rows=data.get('frames',[])
        if data.get('kind')!='motion_frames' or data.get('fps')!=24 or not 5<=len(rows)<=362:
            raise ValueError('动作参考应为24FPS且不超过362帧。')
        frames=[];size=None
        for row in rows:
            path=(source.parent/row['image']).resolve(strict=True)
            if not path.is_relative_to(root) or path.suffix.lower()!='.png':raise ValueError('动作帧路径异常。')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('动作帧内容与入队记录不一致。')
            with Image.open(path) as im:
                if im.width*im.height>1_100_000:raise ValueError('动作参考画布过大。')
                if size is None:size=im.size
                elif im.size!=size:raise ValueError('动作帧画布不一致。')
                frames.append(np.asarray(im.convert('RGB'),dtype=np.float32)/255.)
        return (torch.from_numpy(np.stack(frames)),)
