"""Foreground-only, regional reference palettes. No image warping or RGB channel gains.

Palette prototypes estimate smooth Lab offsets; exported pixels are never quantized.
All frames use the original reference, rather than propagating the previous frame.
"""
import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree
from skimage.color import rgb2lab,lab2rgb

PARTS=('head','upper','lower','feet')
ANALYSIS_WIDTH=256


def boundaries(image,pose):
    pixels=np.asarray(image.convert('RGBA')); ys,xs=np.nonzero(pixels[:,:,3]>220)
    if len(ys)<200: return None
    top,bottom=float(ys.min()),float(ys.max()); height=max(1,bottom-top)
    p=pose.get('joints',{})
    neck=p.get('neck',[0,top+height*.23])[1]
    hips=[p[name][1] for name in ('right_hip','left_hip') if name in p]
    hip=float(np.mean(hips)) if hips else top+height*.57
    cut1=float(np.clip(neck,top+height*.16,top+height*.35))
    cut2=float(np.clip(hip,cut1+height*.12,top+height*.72))
    cut3=max(cut2+height*.08,top+height*.84)
    return [cut1,cut2,min(cut3,bottom-height*.04)],height


def _sample_parts(image,pose):
    cuts=boundaries(image,pose)
    if cuts is None: return {}
    original_width=image.width
    image=image.convert('RGBA').resize((ANALYSIS_WIDTH,round(image.height*ANALYSIS_WIDTH/original_width)),Image.Resampling.BILINEAR)
    pixels=np.asarray(image); scale=ANALYSIS_WIDTH/original_width
    labels=np.searchsorted(np.array(cuts[0])*scale,np.arange(image.height))
    result={}
    for index,name in enumerate(PARTS):
        mask=(pixels[:,:,3]>235)&(labels[:,None]==index)
        colors=pixels[:,:,:3][mask]
        if len(colors)<48: continue
        result[name]=colors
    return result


def _palette(colors):
    # Deterministic median-cut prototypes include only solid foreground pixels.
    colors=colors[::max(1,len(colors)//6000)]
    sample=Image.fromarray(colors[None,:,:].astype(np.uint8),'RGB')
    quantized=sample.quantize(colors=10,method=Image.Quantize.MEDIANCUT)
    entries=sorted(quantized.getcolors(),reverse=True)
    table=np.asarray(quantized.getpalette(),dtype=np.uint8).reshape(-1,3)
    rgbs=[]; weights=[]
    for count,index in entries:
        if count<max(4,len(colors)*.006): continue
        rgbs.append(table[index]); weights.append(count/len(colors))
    if not rgbs: return None
    lab=rgb2lab(np.array(rgbs)[None,:,:]/255.)[0]
    return {'lab':lab.tolist(),'weights':weights}


def _mapping(source,target):
    a=np.asarray(source['lab']);b=np.asarray(target['lab'])
    delta=a[None,:,:]-b[:,None,:]
    distance=np.linalg.norm(delta*np.array([.8,1,1]),axis=2)
    frequency=np.abs(np.log((np.asarray(target['weights'])[:,None]+.005)/(np.asarray(source['weights'])[None,:]+.005)))
    cost=distance+4*frequency
    rows,columns=linear_sum_assignment(cost)
    shifts=np.zeros_like(b); uncertain=[]; pairs=[]
    for row,column in zip(rows,columns):
        raw=a[column]-b[row]; magnitude=float(np.linalg.norm(raw))
        # Unmatched rare colors are left intact. Large ambiguous changes are flagged.
        if magnitude>45:
            uncertain.append(int(row));continue
        if magnitude<3: continue
        shift=np.clip(raw,[-18,-16,-16],[18,16,16])
        # Preserve solid dark outlines; do not lift them to a garment/hair shade.
        if b[row,0]<10 and np.linalg.norm(b[row,1:])<8:
            shift=np.clip(shift,[-1,-2,-2],[1,2,2])
        shifts[row]=shift
        bounded=bool(np.max(np.abs(raw-shift))>.05)
        if bounded and magnitude>30: uncertain.append(int(row))
        pairs.append({'target':int(row),'reference':int(column),'delta_e_before':round(magnitude,3),'bounded':bounded})
    return {'target_lab':b.tolist(),'shift_lab':shifts.tolist(),'reference_lab':a.tolist(),
        'pairs':pairs,'uncertain_prototypes':uncertain}


def palette_plan(paths,poses,reference,base):
    source={name:_palette(colors) for name,colors in _sample_parts(reference,base).items()}
    source={name:palette for name,palette in source.items() if palette is not None}
    records=[]
    for path,pose in zip(paths,poses):
        with Image.open(path) as image: samples=_sample_parts(image,pose)
        regions={}
        for name,colors in samples.items():
            if name in source:
                target=_palette(colors)
                if target is not None: regions[name]=_mapping(source[name],target)
        records.append({'regions':regions,'status':'reference_palette' if regions else 'insufficient_foreground'})
    return {'method':'foreground_regional_reference_lab_v1','reference':'original_reference',
        'alpha_unchanged':True,'geometry_unchanged':True,'background_in_statistics':False,
        'lab_shift_limits':[18,16,16],'reference_palettes':source,'frames':records}


def apply_palette(image,pose,report):
    image=image.convert('RGBA');pixels=np.array(image);cuts=boundaries(image,pose)
    if cuts is None or not report.get('regions'):
        return image.copy(),{'changed_pixels':0,'status':'insufficient_foreground','requires_review':True}
    yy,xx=np.nonzero(pixels[:,:,3]>0)
    lab=rgb2lab(pixels[yy,xx,:3][None,:,:]/255.)[0]
    all_reference=np.concatenate([np.asarray(mapping['reference_lab']) for mapping in report['regions'].values()])
    global_tree=cKDTree(all_reference);global_distance=global_tree.query(lab)[0]
    delta_sum=np.zeros_like(lab);weight_sum=np.zeros(len(lab)); width=max(2,cuts[1]*.025)
    region_reports={}
    edges=[-np.inf,*cuts[0],np.inf]
    for index,name in enumerate(PARTS):
        mapping=report['regions'].get(name)
        if not mapping: continue
        left,right=edges[index:index+2]
        weight=np.minimum(np.clip((yy-left+width)/(2*width),0,1),np.clip((right-yy+width)/(2*width),0,1))
        select=np.flatnonzero(weight>0)
        if not len(select): continue
        points=lab[select];prototypes=np.asarray(mapping['target_lab']);shifts=np.asarray(mapping['shift_lab'])
        k=min(3,len(prototypes));distance,labels=cKDTree(prototypes).query(points,k=k)
        if k==1: distance=distance[:,None];labels=labels[:,None]
        blend=np.exp(-((distance-distance[:,:1])/7)**2)
        change=(shifts[labels]*blend[:,:,None]).sum(axis=1)/blend.sum(axis=1)[:,None]
        # Already matching source colors, including accents and black linework, stay exact.
        source_distance=cKDTree(np.asarray(mapping['reference_lab'])).query(points)[0]
        keep=(source_distance<2.5)|((index>=2)&(global_distance[select]<2.5))|(distance[:,0]>35)
        change[keep]=0
        delta_sum[select]+=change*weight[select,None];weight_sum[select]+=weight[select]
        uncertain=np.isin(labels[:,0],mapping['uncertain_prototypes'])&(distance[:,0]<35)&(global_distance[select]>8)
        region_reports[name]={'uncertain_pixels':int(uncertain.sum()),
            'median_palette_distance_before':round(float(np.median(source_distance)),3)}
    delta_sum/=np.maximum(1e-6,weight_sum[:,None])
    changed=np.linalg.norm(delta_sum,axis=1)>.6
    if changed.any():
        result=lab2rgb((lab[changed]+delta_sum[changed])[None,:,:])[0]
        pixels[yy[changed],xx[changed],:3]=np.clip(result*255,0,255).round().astype(np.uint8)
    resulting_lab=rgb2lab(pixels[yy,xx,:3][None,:,:]/255.)[0]
    global_after=global_tree.query(resulting_lab)[0]
    return Image.fromarray(pixels),{'method':'foreground_regional_reference_lab_v1',
        'changed_pixels':int(changed.sum()),'alpha_unchanged':True,'geometry_unchanged':True,
        'median_palette_distance_before':round(float(np.median(global_distance)),3),
        'median_palette_distance_after':round(float(np.median(global_after)),3),
        'metric_scope':'nearest foreground palette; not semantic identity or full quality',
        'requires_review':any(part['uncertain_pixels']>100 for part in region_reports.values()),'regions':region_reports}
