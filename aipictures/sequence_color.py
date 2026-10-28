"""Conservative temporal exposure/cast correction on opaque subject regions only."""
import numpy as np
from PIL import Image


def signature(image,pose):
    image=image.convert('RGBA'); width=192; height=round(image.height*width/image.width)
    pixels=np.asarray(image.resize((width,height),Image.Resampling.BILINEAR))
    rgb=pixels[:,:,:3].astype(float); alpha=pixels[:,:,3]
    yy,xx=np.mgrid[:height,:width]; scale=width/image.width
    p={name:np.array(point[:2])*scale for name,point in pose['joints'].items()}
    total_height=max(1,p['right_ankle'][1]-p['nose'][1]); radius=max(3,total_height*.035)
    def capsule(a,b,r):
        direction=b-a; denominator=max(.001,float(direction@direction))
        t=np.clip(((xx-a[0])*direction[0]+(yy-a[1])*direction[1])/denominator,0,1)
        return (xx-a[0]-t*direction[0])**2+(yy-a[1]-t*direction[1])**2<r*r
    hip=(p['right_hip']+p['left_hip'])/2; neck=p['neck']; nose=p['nose']
    head=nose+(neck-nose)*.12+np.array([-radius*.65,-radius*.25])
    masks={'head':capsule(head,head,radius*1.4),
        'torso':capsule(neck+(hip-neck)*.25,neck+(hip-neck)*.80,radius*1.05),
        'legs':np.zeros((height,width),bool)}
    for side in ('right','left'):
        a=p[side+'_hip']; b=p[side+'_knee']; c=p[side+'_ankle']
        masks['legs']|=capsule(a+(b-a)*.25,b,radius*.75)|capsule(b,b+(c-b)*.6,radius*.65)
    valid=(alpha>220)&(rgb.max(axis=2)>24)
    result={}
    for name,mask in masks.items():
        values=rgb[mask&valid]
        if len(values)<16: continue
        # Log-space regional medians are insensitive to different silhouette areas.
        log_rgb=np.median(np.log(values+12),axis=0)
        result[name]={'log_rgb':log_rgb.tolist(),'pixels':len(values)}
    foreground=alpha>220
    result['clipped_fraction']=float(((rgb.min(axis=2)>250)&foreground).sum()/max(1,foreground.sum()))
    return result


def correction_plan(signatures):
    if len(signatures)<3: return [{'gain':[1.,1.,1.],'status':'insufficient_frames'} for _ in signatures]
    targets={}
    for name in ('head','torso','legs'):
        values=[item[name]['log_rgb'] for item in signatures if name in item]
        if len(values)>=3: targets[name]=np.median(values,axis=0)
    clipping=np.median([item['clipped_fraction'] for item in signatures]); reports=[]
    for item in signatures:
        deltas=[np.array(item[name]['log_rgb'])-target for name,target in targets.items() if name in item]
        report={'gain':[1.,1.,1.],'status':'stable','clipped_fraction':item['clipped_fraction']}
        if item['clipped_fraction']>clipping+.05: report['warning']='highlight_clipping_may_be_irrecoverable'
        if len(deltas)<2: report['status']='insufficient_regions'; reports.append(report); continue
        median=np.median(deltas,axis=0)
        agreeing=[delta for delta in deltas if np.max(np.abs(delta-median))<.13]
        if len(agreeing)<2 or np.max(np.abs(median))<.075:
            reports.append(report); continue
        # Only a concordant change across distinct body regions may move the whole palette.
        median=np.median(agreeing,axis=0)
        if sum(np.max(np.abs(delta))>.06 for delta in agreeing)<2:
            reports.append(report); continue
        # Independent channel gains can turn skin green when an arm hides part of
        # the torso. Only concordant exposure drift is safe to correct automatically.
        if np.ptp(median)>.035:
            report['status']='color_cast_requires_review'; reports.append(report); continue
        exposure=float(np.median(median)); gain=np.full(3,float(np.clip(np.exp(-exposure),.80,1.20)))
        report.update(gain=gain.tolist(),status='corrected',agreeing_regions=len(agreeing),
            bounded=bool(abs(np.exp(-exposure)-gain[0])>.0001))
        reports.append(report)
    return reports


def apply_correction(image,report):
    if report['status']!='corrected': return image.copy()
    pixels=np.array(image.convert('RGBA')); foreground=pixels[:,:,3]>0
    adjusted=np.clip((pixels[:,:,:3].astype(float)+12)*np.array(report['gain'])-12,0,255).round().astype(np.uint8)
    pixels[foreground,:3]=adjusted[foreground]
    return Image.fromarray(pixels)


def plan_files(paths,poses):
    records=[]
    for path,pose in zip(paths,poses):
        with Image.open(path) as image: records.append(signature(image,pose))
    return {'method':'temporal_regional_exposure_v2','reference':'sequence_regional_median',
        'alpha_unchanged':True,'gain_bounds':[.8,1.2], 'frames':correction_plan(records)}
