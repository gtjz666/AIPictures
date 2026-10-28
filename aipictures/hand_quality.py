"""Reference-guarded novel hue repair in detected skin hands; no alpha or geometry edits."""
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree
from .pose_condition import hand_points


def hand_mask(size,points,padding=10):
    valid=[tuple(point[:2]) for point in points if point[2]>.25]
    mask=Image.new('L',size)
    if len(valid)<10: return np.zeros((size[1],size[0]),bool)
    from scipy.spatial import ConvexHull,QhullError
    try:
        hull=ConvexHull(valid); ImageDraw.Draw(mask).polygon([valid[index] for index in hull.vertices],fill=255)
    except QhullError: return np.zeros((size[1],size[0]),bool)
    mask=np.asarray(mask)>0
    if padding: mask=ndimage.maximum_filter(mask,size=padding*2+1)
    return mask


def repair_reference_hands(image,reference,rig,base):
    src=np.asarray(reference.convert('RGBA')); rgba=np.array(image.convert('RGBA'))
    if image.size!=reference.size: raise ValueError('手部校验画布不一致。')
    template=base.get('visible_hand_keypoints',[])
    source_mask=hand_mask(image.size,template,4)&(src[:,:,3]>220)
    source_colors=src[:,:,:3][source_mask]
    if len(source_colors)<40: return image.copy(),{'changed_pixels':0,'reason':'no_reliable_hand_reference'}
    values=source_colors.astype(float)
    flesh=(values[:,0]>60)&(values[:,0]>values[:,1]+6)&(values[:,1]>values[:,2]+3)&(values[:,2]>values[:,1]*.55)
    if flesh.sum()<max(35,len(values)*.30): return image.copy(),{'changed_pixels':0,'reason':'reference_is_not_skin_hand'}
    skin=values[flesh]; skin_color=np.median(skin,axis=0)
    skin_hue=float(np.median(60*(skin[:,1]-skin[:,2])/np.maximum(1,skin[:,0]-skin[:,2])))
    # The whole reference-hand palette protects accessories already present in the input.
    palette=np.unique((source_colors//8)*8,axis=0).astype(float); tree=cKDTree(palette)
    all_colors=src[:,:,:3][src[:,:,3]>220]
    bins,counts=np.unique((all_colors//16)*16,axis=0,return_counts=True)
    common=bins[counts>=max(20,len(all_colors)*.001)]
    common_tree=cKDTree(common.astype(float)) if len(common) else None
    region=np.zeros(source_mask.shape,bool)
    yy,xx=np.mgrid[:image.height,:image.width]
    for side in ('left','right'):
        region|=hand_mask(image.size,hand_points(rig,base,side),16)
        wrist=rig['joints'][side+'_wrist']
        # Generated wrists can drift from the control map; bounded neighborhood search
        # catches leaked hues without treating the entire character as a hand region.
        region|=(xx-wrist[0])**2+(yy-wrist[1])**2<90**2
    # A missed arm can be farther from its requested wrist. Search the torso/upper-leg
    # height too, but only repair small foreign hues adjacent to matching skin below.
    top=rig['joints']['neck'][1]; bottom=max(rig['joints'][side+'_knee'][1] for side in ('left','right'))
    region|=(yy>top)&(yy<bottom)
    region&=rgba[:,:,3]>120
    ys,xs=np.nonzero(region)
    if not len(xs): return image.copy(),{'changed_pixels':0,'reason':'no_visible_hand_pixels'}
    rgb=rgba[:,:,:3].astype(float); colors=rgb[ys,xs]; distance=tree.query(colors)[0]
    chroma=colors.max(axis=1)-colors.min(axis=1)
    red_dominant=(colors[:,0]>=colors[:,1])&(colors[:,0]>=colors[:,2])
    hue=60*(colors[:,1]-colors[:,2])/np.maximum(1,colors[:,0]-colors[:,2])
    foreign_hue=(~red_dominant)|(np.abs(hue-skin_hue)>14)
    novel=((distance>60)|((distance>18)&foreign_hue&(chroma/np.maximum(1,colors.max(axis=1))>.30)))&(chroma>40)
    if common_tree is not None: novel&=common_tree.query(colors)[0]>18
    candidates=np.zeros(region.shape,bool); candidates[ys[novel],xs[novel]]=True
    labels,count=ndimage.label(candidates); changed=0; flagged=0
    for index in range(1,count+1):
        component=labels==index; area=int(component.sum())
        if area<6: continue
        if area>max(1000,len(source_colors)*.8): flagged+=area; continue
        ring=ndimage.binary_dilation(component,iterations=10)&region&~candidates
        neighbors=rgb[ring]
        healthy=(neighbors[:,0]>60)&(neighbors[:,0]>neighbors[:,1]+6)&(neighbors[:,1]>neighbors[:,2]+3)&(neighbors[:,2]>neighbors[:,1]*.55)
        healthy&=np.abs(60*(neighbors[:,1]-neighbors[:,2])/np.maximum(1,neighbors[:,0]-neighbors[:,2])-skin_hue)<12
        if healthy.sum()<8: flagged+=area; continue
        color=np.median(neighbors[healthy],axis=0)
        # Bound the replacement to the same reference skin family, allowing local shading.
        shade=np.clip(color.mean()/max(1,skin_color.mean()),.72,1.15)
        rgba[component,:3]=np.clip(skin_color*shade,0,255).round().astype(np.uint8); changed+=area
    return Image.fromarray(rgba),{'changed_pixels':changed,'unresolved_pixels':flagged,
        'method':'reference_skin_novel_hue_guard','alpha_unchanged':True,
        'geometry_repaired':False,'note':'仅校正原图没有的异常手部颜色；形状和多余物体仍需检查。'}
