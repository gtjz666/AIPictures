"""Isolated DACoN paint-bucket experiment; never used by the application.

Uses external, unmodified author repositories and weights in a research environment.
The target RGB hues never enter matching or filling: only its alpha and extracted
line drawing are consumed. Fill RGB values are actual pixels of the reference.
"""
import argparse
import functools
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage
from skimage.color import rgb2lab
from aipictures.storage import write_json


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def make_segments(gray,alpha,threshold=180,gap_close=1):
    """Closed interiors from line drawing and this image's own foreground mask."""
    mask=alpha>127
    ink=(gray<threshold)&mask
    if gap_close:ink=ndimage.binary_closing(ink,iterations=gap_close)&mask
    ink|=mask&~ndimage.binary_erosion(mask)
    labels,count=ndimage.label(mask&~ink)
    sizes=np.bincount(labels.ravel());small=sizes<6;small[0]=False
    labels[small[labels]]=0
    _,labels=np.unique(labels,return_inverse=True);labels=labels.reshape(mask.shape).astype('int32')
    return labels,ink,{'regions':int(labels.max()),'interior_fraction':float((labels>0).sum()/max(1,mask.sum())),
        'largest_region_fraction':float(np.bincount(labels[labels>0]).max(initial=0)/max(1,mask.sum()))}


def reference_colors(rgba,labels):
    colors=[]
    for index in range(1,int(labels.max())+1):
        pixels=rgba[labels==index,:3]
        # A sampled medoid stays an actual reference RGB, unlike a synthetic mean.
        median=np.median(pixels,axis=0)
        colors.append(pixels[np.argmin(np.square(pixels.astype(float)-median).sum(axis=1))])
    return np.asarray(colors,dtype=np.uint8)


def line_features(gray,ink,labels,device):
    import torch
    # Match author RGBA line convention: transparent white off the black lines.
    h,w=gray.shape;line=np.ones((h,w,4),dtype=np.float32)
    line[:,:,:3][ink]=0;line[:,:,3]=ink.astype(np.float32)
    return (torch.from_numpy(line).permute(2,0,1).unsqueeze(0).to(device),
        torch.from_numpy(labels.astype('int64')).unsqueeze(0).to(device),
        torch.tensor([labels.max()],dtype=torch.int64,device=device))


def load_models(args):
    import torch
    import torch.nn as nn
    torch.set_num_threads(args.threads)
    sys.path.insert(0,str(args.vendor/'dinov2'))
    sys.path.insert(0,str(args.vendor/'DACoN'/'dacon'))
    from dinov2.hub.backbones import dinov2_vitl14
    from models import DACoNModel
    original=torch.hub.load
    def local_dino(repo,name,*a,**kw):
        if repo!='facebookresearch/dinov2' or name!='dinov2_vitl14':raise ValueError('Unexpected model request')
        model=dinov2_vitl14(pretrained=False)
        model.load_state_dict(torch.load(args.models/'dinov2_vitl14_pretrain.pth',map_location='cpu',weights_only=True),strict=True)
        return model
    torch.hub.load=local_dino
    config=json.loads((args.output/'model-config.json').read_text('utf-8'))
    try:model=DACoNModel(config,'1_1')
    finally:torch.hub.load=original
    state=torch.load(args.models/'dacon_v1_1.pth',map_location='cpu',weights_only=True)
    missing,unexpected=model.load_state_dict(state,strict=False)
    # Authors omit the frozen DINO backbone from the checkpoint. It was loaded
    # separately with strict=True above. All trained DACoN tensors must match.
    if unexpected or any(not name.startswith('dino.') for name in missing):
        raise RuntimeError({'missing':missing,'unexpected':unexpected})
    model=model.to(args.device).eval()
    sys.path.insert(0,str(args.aux/'src'))
    from custom_controlnet_aux.lineart_anime import UnetGenerator
    net=UnetGenerator(3,1,8,64,norm_layer=functools.partial(nn.InstanceNorm2d,affine=False,track_running_stats=False))
    state=torch.load(args.models/'netG.pth',map_location='cpu',weights_only=True)
    net.load_state_dict({k.removeprefix('module.'):v for k,v in state.items()},strict=True)
    return model,net.to(args.device).eval()


def extract_line(image,net,device):
    import torch
    import torch.nn.functional as F
    rgba=np.asarray(image.convert('RGBA'))
    alpha=rgba[:,:,3:4]/255.;rgb=rgba[:,:,:3]*alpha+255*(1-alpha)
    tensor=torch.from_numpy(rgb.astype('float32')).permute(2,0,1).unsqueeze(0).to(device)/127.5-1
    # Author detector uses a 256-aligned input; portrait images retain aspect ratio.
    h,w=rgba.shape[:2];hh=256*int(np.ceil(h/256));ww=256*int(np.ceil(w/256))
    tensor=F.interpolate(tensor,size=(hh,ww),mode='bicubic',align_corners=False)
    with torch.inference_mode():out=(net(tensor)+1)*127.5
    out=F.interpolate(out,size=(h,w),mode='area')[0,0].cpu().numpy()
    return np.clip(out,0,255).round().astype('uint8')


def measure(result,truth):
    a=np.asarray(result);b=np.asarray(truth);mask=b[:,:,3]>235
    x=rgb2lab(a[mask,:3][None,:,:]/255.)[0];y=rgb2lab(b[mask,:3][None,:,:]/255.)[0]
    delta=np.linalg.norm(x-y,axis=1)
    return {'scope':'known self/controlled-warp ground truth only','mean_lab_distance':round(float(delta.mean()),3),
        'fraction_delta_e_above_10':round(float((delta>10).mean()),4),
        'alpha_bit_exact':bool(np.array_equal(a[:,:,3],b[:,:,3]))}


def thumbnail(image,size=(220,430)):
    image=image.convert('RGBA');box=image.getchannel('A').getbbox()
    if box:image=image.crop(box)
    image.thumbnail(size,Image.Resampling.LANCZOS)
    bg=Image.new('RGBA',size,'#ededed');bg.alpha_composite(image,((size[0]-image.width)//2,(size[1]-image.height)//2))
    return bg.convert('RGB')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('suite',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--vendor',type=Path,default=Path('D:/ComfyResearch/reference-color'))
    parser.add_argument('--models',type=Path,default=Path('D:/ComfyModels/reference-color'))
    parser.add_argument('--aux',type=Path,default=Path('D:/Local Comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux'))
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu');parser.add_argument('--threads',type=int,default=6)
    parser.add_argument('--threshold',type=int,default=180);parser.add_argument('--gap-close',type=int,default=1)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    config={'feats_dim':128,'dino_model_type':'dinov2_vitl14','dino_input_size':[518,518],
        'unet_input_size':[512,512],'unet_input_dim':3,'unet_hidden_dim_list':[64,128,256,512],'segment_pool_size':[512,512]}
    write_json(args.output/'model-config.json',config)
    print('Loading research models',flush=True);model,net=load_models(args)
    import torch
    suite=json.loads(args.suite.read_text('utf-8'));results=[]
    for case in suite['cases']:
        started=time.monotonic();out=args.output/case['id'];out.mkdir(exist_ok=True)
        reference=Image.open(case['reference']).convert('RGBA');reference.save(out/'reference.png')
        gray=extract_line(reference,net,args.device)
        rlabels,rink,rinfo=make_segments(gray,np.asarray(reference)[:,:,3],args.threshold,args.gap_close)
        colors=reference_colors(np.asarray(reference),rlabels)
        Image.fromarray(gray).save(out/'reference-line.png');np.save(out/'reference-regions.npy',rlabels)
        write_json(out/'reference-colors.json',colors.tolist())
        with torch.inference_mode():rf,_=model._process_single(*line_features(gray,rink,rlabels,args.device))
        # Reference outline color, also sampled rather than generated.
        pixels=np.asarray(reference);solid=pixels[pixels[:,:,3]>235,:3]
        outline=solid[np.argmin(np.mean(solid,axis=1))]
        frames=[]
        for index,target_spec in enumerate(case['targets']):
            target=Image.open(target_spec['image']).convert('RGBA');array=np.asarray(target)
            tgray=extract_line(target,net,args.device)
            labels,ink,info=make_segments(tgray,array[:,:,3],args.threshold,args.gap_close)
            with torch.inference_mode():
                tf,_=model._process_single(*line_features(tgray,ink,labels,args.device))
                similarities=model.get_seg_cos_sim(rf.unsqueeze(1),tf.unsqueeze(1))[0]
                best=similarities.argmax(dim=-1).cpu().numpy()
                top=similarities.topk(min(2,len(colors)),dim=-1).values.cpu().numpy()
            fill=np.array(array);foreground=array[:,:,3]>0
            # Transfer nearest interior labels only across the line width, keeping
            # this target's exact silhouette and transparent alpha.
            nearest=ndimage.distance_transform_edt(labels==0,return_distances=False,return_indices=True)
            expanded=labels[nearest[0],nearest[1]]
            fill[foreground,:3]=colors[best[np.maximum(0,expanded[foreground]-1)]]
            fill[ink,:3]=outline
            result=Image.fromarray(fill);result.save(out/f'{index:03d}-strict-fill.png')
            target.save(out/f'{index:03d}-target.png');Image.fromarray(tgray).save(out/f'{index:03d}-line.png')
            np.save(out/f'{index:03d}-regions.npy',labels)
            record={'index':index,'target':target_spec['image'],'regions':info,'reference_regions':rinfo,
                'alpha_bit_exact':bool(np.array_equal(fill[:,:,3],array[:,:,3])),
                'fill_rgb_from_reference_only':True,'matched_reference_region':best.tolist(),
                'similarity_margin_median':float(np.median(top[:,0]-top[:,1])) if top.shape[1]>1 else None}
            if target_spec.get('ground_truth'):record['ground_truth']=measure(result,Image.open(target_spec['ground_truth']).convert('RGBA'))
            frames.append(record)
            panel=Image.new('RGB',(880,470),'white');draw=ImageDraw.Draw(panel)
            for col,(label,img) in enumerate([('Reference',reference),('Target / truth if known',target),('Extracted lines',Image.fromarray(tgray).convert('RGBA')),('Reference RGB fill',result)]):
                panel.paste(thumbnail(img),(col*220,35));draw.text((col*220+5,10),label,fill='black')
            panel.save(out/f'{index:03d}-comparison.jpg')
            print(case['id'],index,'regions',info['regions'],record.get('ground_truth',{}),flush=True)
            write_json(out/'frames.json',frames)
        record={'case':case['id'],'category':case['category'],'frames':frames,'elapsed_seconds':round(time.monotonic()-started,2)}
        results.append(record);write_json(args.output/'results.json',{'method':'DACoN_v1_1_strict_reference_RGB_fill','default_enabled':False,
            'memory_temperature_monitoring':False,'time_limit':None,'cases':results})
    print('Complete:',args.output,flush=True)


if __name__=='__main__':main()
