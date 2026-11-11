"""CPU-only geometric depth extraction; independent of image/text model processes."""
import json,sys,time,os
from pathlib import Path

def validate(request):
    for key in ('width','height'):
        n=request[key]
        if type(n)!=int or not 256<=n<=2048 or n%16:raise ValueError('Invalid structure canvas dimensions')

def run(request):
    validate(request)
    os.environ['CUDA_VISIBLE_DEVICES']='-1'
    import hashlib
    from PIL import Image,ImageOps
    import numpy as np
    started=time.monotonic();out=Path(request['output']);out.mkdir(parents=True,exist_ok=False)
    source=Path(request['source']);raw=source.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    weights=Path(request['weights']);expected='715fade13be8f229f8a70cc02066f656f2423a59effd0579197bbf57860e1378'
    if hashlib.sha256(weights.read_bytes()).hexdigest()!=expected:raise ValueError('Depth model checksum mismatch')
    with Image.open(source) as im:
        if im.width*im.height>40_000_000 or getattr(im,'n_frames',1)!=1:raise ValueError('Structure source must be a static image under 40 megapixels')
        if max(im.size)/min(im.size)>4:raise ValueError('结构参考图过于狭长，请裁切主体后再生成。')
        rgba=ImageOps.exif_transpose(im).convert('RGBA');rgb=Image.new('RGB',rgba.size,'white');rgb.paste(rgba,mask=rgba.getchannel('A'))
    sys.path.insert(0,request['aux_source'])
    import torch
    torch.set_num_threads(4)
    from custom_controlnet_aux.depth_anything_v2 import DepthAnythingV2,model_configs
    model=DepthAnythingV2(**model_configs['depth_anything_v2_vits.pth'])
    model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True),strict=True);model.eval()
    import cv2
    from custom_controlnet_aux.depth_anything_v2.dpt import Compose,Resize,NormalizeImage,PrepareForNet
    transform=Compose([Resize(width=518,height=518,resize_target=False,keep_aspect_ratio=True,ensure_multiple_of=14,resize_method='lower_bound',image_interpolation_method=cv2.INTER_CUBIC),
        NormalizeImage(mean=[.485,.456,.406],std=[.229,.224,.225]),PrepareForNet()])
    pixels=transform({'image':np.array(rgb)/255.})['image']
    tensor=torch.from_numpy(pixels).unsqueeze(0).float().to('cpu')
    assert tensor.device.type=='cpu' and next(model.parameters()).device.type=='cpu'
    with torch.inference_mode():
        predicted=model(tensor,20.)
        depth=torch.nn.functional.interpolate(predicted[:,None],(rgb.height,rgb.width),mode='bilinear',align_corners=True)[0,0].numpy()
    if not np.isfinite(depth).all() or float(depth.max()-depth.min())<1e-5:raise ValueError('Invalid/flat depth prediction')
    depth=((depth-depth.min())/(depth.max()-depth.min())*255).round().astype(np.uint8)
    native=Image.fromarray(depth).convert('RGB');native.save(out/'depth-native.png')
    width,height=request['width'],request['height'];fitted=ImageOps.contain(native,(width,height),Image.Resampling.BICUBIC)
    offset=((width-fitted.width)//2,(height-fitted.height)//2);canvas=Image.new('RGB',(width,height),'black');canvas.paste(fitted,offset);canvas.save(out/'depth.png')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:raise ValueError('Reference changed during extraction')
    result=dict(source=str(source),source_sha256=sha,depth=str(out/'depth.png'),model_sha256=expected,
        input_size=list(rgb.size),canvas=[width,height],fitted_size=list(fitted.size),offset=list(offset),device='cpu',
        elapsed_seconds=time.monotonic()-started,meaning='relative inverse depth, near white / far black',anatomy_assumed=False)
    (out/'structure.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)

if __name__=='__main__':run(json.loads(Path(sys.argv[1]).read_text('utf-8')))
