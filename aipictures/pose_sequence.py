"""Lossless multi-page pose input for ComfyUI's native LoadImage batch loader."""
from pathlib import Path
from PIL import Image
from .workflow_library import digest


def pack_poses(paths, target):
    paths=[Path(path) for path in paths];target=Path(target)
    if not paths:raise ValueError('缺少连续姿态图片。')
    images=[]
    try:
        for path in paths:
            with Image.open(path) as source:images.append(source.convert('RGB'))
        if any(image.size!=images[0].size for image in images):
            raise ValueError('连续姿态画布不一致，不能打包。')
        target.parent.mkdir(parents=True,exist_ok=True)
        images[0].save(target,save_all=True,append_images=images[1:],compression='tiff_deflate')
        with Image.open(target) as packed:
            if packed.n_frames!=len(images):raise ValueError('无损姿态包帧数不一致。')
            for index,expected in enumerate(images):
                packed.seek(index)
                if packed.convert('RGB').tobytes()!=expected.tobytes():
                    raise ValueError('无损姿态包像素不一致。')
        return {'format':'multipage_tiff','frames':len(images),'canvas':list(images[0].size),
                'sha256':digest(target),'rgb_pixel_exact':True,'frames_blended':False,
                'native_loader':'LoadImage','path':str(target),'source_files':[str(p) for p in paths]}
    finally:
        for image in images:image.close()
