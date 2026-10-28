"""Bounded color-leak repair for reference-white footwear, never alpha or limb topology."""
import numpy as np
from scipy import ndimage
from PIL import Image


def foot_region(size,rig):
    width,height=size; mask=np.zeros((height,width),dtype=bool); points=rig['joints']
    for side in ('right','left'):
        ankle=points[side+'_ankle']; knee=points[side+'_knee']; heel=points[side+'_heel']; toe=points[side+'_toe']
        top=min(ankle[1]-45,knee[1]+(ankle[1]-knee[1])*.46)
        left=max(0,int(min(ankle[0],heel[0],toe[0]))-40); right=min(width,int(max(ankle[0],heel[0],toe[0]))+40)
        mask[max(0,int(top)):min(height,int(max(heel[1],toe[1],ankle[1]))+25),left:right]=True
    return mask


def repair_light_footwear(image,reference,rig,base_rig):
    """Only remove blue/cyan pose-colored patches absent from light reference footwear.

    Dark/colored footwear, genuine blue reference colors and unknown large regions are
    left untouched. Preserve the original matte and every pixel outside the small mask.
    """
    rgba=np.array(image.convert('RGBA')); src=np.asarray(reference.convert('RGBA'))
    if image.size!=reference.size: raise ValueError('足部校验要求参考图与帧使用同一画布。')
    ref_mask=foot_region(reference.size,base_rig)&(src[:,:,3]>200)
    pixels=src[:,:,:3].astype(np.int16); opaque=max(1,int(ref_mask.sum()))
    blue=(pixels[:,:,2]>pixels[:,:,0]+20)&(pixels[:,:,2]>pixels[:,:,1]+10)&(pixels[:,:,2]>75)&ref_mask
    if blue.sum()>max(8,opaque*.002): return image.copy(),{'changed_pixels':0,'reason':'reference_contains_blue_footwear'}
    bright=(pixels.min(axis=2)>165)&((pixels.max(axis=2)-pixels.min(axis=2))<65)&ref_mask
    if bright.sum()<max(100,opaque*.12): return image.copy(),{'changed_pixels':0,'reason':'not_light_reference_footwear'}
    rgb=rgba[:,:,:3].astype(np.int16); region=foot_region(image.size,rig)&(rgba[:,:,3]>100)
    strong=(rgb[:,:,2]>rgb[:,:,0]+25)&(rgb[:,:,2]>rgb[:,:,1]+20)&(rgb[:,:,2]>90)&region
    weak=(rgb[:,:,2]>rgb[:,:,0]+20)&(rgb[:,:,2]>rgb[:,:,1]+10)&(rgb[:,:,2]>75)&region
    labels,count=ndimage.label(weak); repaired=np.zeros(region.shape,dtype=bool)
    unresolved=0
    for index in range(1,count+1):
        component=labels==index
        if (component&strong).sum()<4: continue
        if component.sum()>max(1600,opaque*.10): unresolved+=int(component.sum()); continue
        ring=ndimage.binary_dilation(component,iterations=6)&~weak&region
        neutral=(rgb.min(axis=2)>165)&((rgb.max(axis=2)-rgb.min(axis=2))<65)&ring&(rgba[:,:,3]>220)
        if neutral.sum()<8: unresolved+=int(component.sum()); continue
        color=np.median(rgba[:,:,:3][neutral],axis=0).astype(np.uint8)
        rgba[component,:3]=color; repaired|=component
    return Image.fromarray(rgba),{'changed_pixels':int(repaired.sum()),'unresolved_pixels':unresolved,
        'method':'reference_guarded_local_neutral_fill','alpha_unchanged':True,
        'scope':'blue_color_leak_in_light_footwear_only'}
