"""Inspect sprite canvas boundaries without modifying alpha, colors or placement."""
from PIL import Image


def canvas_review(image: Image.Image) -> dict:
    box=image.convert('RGBA').getchannel('A').point(lambda value:255 if value>16 else 0).getbbox()
    if box is None:return {'status':'empty','bbox':None,'margins':None}
    margins=[box[0],box[1],image.width-box[2],image.height-box[3]]
    return {'status':'boundary' if min(margins)<=2 else 'inside','bbox':list(box),'margins':margins}


def boundary_warnings(frames: list[dict]) -> list[str]:
    messages=[]
    for frame in frames:
        status=frame.get('canvas_review',{}).get('status')
        if status=='boundary':messages.append(f'第 {frame["index"]+1} 帧主体贴近画布边界，请检查头顶或肢体是否截断。')
        elif status=='empty':messages.append(f'第 {frame["index"]+1} 帧没有可见主体，请检查原图与透明处理。')
    return messages
