"""Reference-guarded green-cast correction for violet/blue dark hair only."""
import numpy as np
from PIL import Image
from skimage.color import rgb2lab,lab2rgb


def hair_region(image):
    array=np.asarray(image.convert('RGBA')); height,width=array.shape[:2]; yy,xx=np.mgrid[:height,:width]
    ys,xs=np.nonzero(array[:,:,3]>150)
    if not len(ys): return np.zeros((height,width),bool)
    top,bottom=int(ys.min()),int(ys.max()); length=max(1,bottom-top)
    head=(yy<top+length*.22)&(array[:,:,3]>150)
    head_x=xx[head]
    if not len(head_x): return head
    front=float(np.percentile(head_x,98)); back=float(np.percentile(head_x,2))
    return head&((yy<top+length*.10)|(xx<front-(front-back)*.25))


def repair_reference_hair(image,reference,rig,base):
    source=np.asarray(reference.convert('RGBA')); output=np.array(image.convert('RGBA'))
    if reference.size!=image.size: raise ValueError('参考配色校验画布不一致。')
    region=hair_region(reference)&(source[:,:,3]>220)
    colors=source[:,:,:3][region]; dark=colors[colors.max(axis=1)<145]
    if len(dark)<max(100,len(colors)*.3):
        return image.copy(),{'changed_pixels':0,'reason':'no_reliable_dark_hair_palette'}
    reference_lab=rgb2lab(dark[None,:,:]/255.)[0]; chroma=np.median(reference_lab[:,1:],axis=0)
    if chroma[0]<3 or chroma[1]>-3:
        return image.copy(),{'changed_pixels':0,'reason':'not_violet_blue_reference_hair'}
    if np.array_equal(source,output): return image.copy(),{'changed_pixels':0,'reason':'identical_reference'}
    mask=hair_region(image)&(output[:,:,3]>150)&(output[:,:,:3].max(axis=2)<165)
    y,x=np.nonzero(mask); values=output[y,x,:3]
    if not len(y): return image.copy(),{'changed_pixels':0,'reason':'no_visible_hair_pixels'}
    lab=rgb2lab(values[None,:,:]/255.)[0]
    novel=(lab[:,1]<chroma[0]-9)&(lab[:,2]>chroma[1]+4)
    lab[novel,1:]=chroma
    if novel.any(): output[y[novel],x[novel],:3]=np.clip(lab2rgb(lab[novel][None,:,:])[0]*255,0,255).round().astype(np.uint8)
    return Image.fromarray(output),{'changed_pixels':int(novel.sum()),'alpha_unchanged':True,
        'method':'reference_violet_hair_green_cast_guard','luminance_retained':True,'face_area_excluded':True}
