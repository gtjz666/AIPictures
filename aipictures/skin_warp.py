"""Continuous limb meshes with source-derived colors and one shared alpha matte."""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image,ImageChops,ImageFilter,ImageDraw
from scipy import ndimage
from scipy.spatial import ConvexHull
from skimage.transform import PiecewiseAffineTransform,warp

from .reference_analysis import SIZE,opaque_reference


def line_distance(x,y,a,b):
    vx,vy=b[0]-a[0],b[1]-a[1]
    t=np.clip(((x-a[0])*vx+(y-a[1])*vy)/max(1,vx*vx+vy*vy),0,1)
    return np.hypot(x-a[0]-t*vx,y-a[1]-t*vy)


def mesh_warp(image,source,target,width=60):
    """One continuous piecewise affine strip, avoiding hard cuts at elbow/knee."""
    def rows(points):
        values=[]
        for i in range(len(points)-1):
            for t in (0,.25,.5,.75): values.append((1-t)*points[i]+t*points[i+1])
        values.append(points[-1]); values=np.asarray(values)
        tangents=np.gradient(values,axis=0)
        tangents/=np.maximum(1e-6,np.linalg.norm(tangents,axis=1))[:,None]
        normals=np.column_stack((tangents[:,1],-tangents[:,0]))
        return np.asarray([center+normal*offset for center,normal in zip(values,normals) for offset in (-width,0,width)])
    source=np.asarray(source,dtype=float); target=np.asarray(target,dtype=float)
    inverse=PiecewiseAffineTransform.from_estimate(rows(target),rows(source))
    rgba=np.asarray(image,dtype=np.float32)/255
    rgba[:,:,:3]*=rgba[:,:,3,None]
    warped=warp(rgba,inverse,output_shape=(SIZE[1],SIZE[0]),order=1,mode='constant',cval=0,preserve_range=True)
    alpha=warped[:,:,3]
    rgb=np.divide(warped[:,:,:3],alpha[:,:,None],out=np.zeros_like(warped[:,:,:3]),where=alpha[:,:,None]>.001)
    output=np.concatenate((rgb,alpha[:,:,None]),axis=2)
    return Image.fromarray(np.uint8(np.clip(output*255,0,255)))


def translated(image,dx,dy):
    return image.transform(SIZE,Image.Transform.AFFINE,(1,0,-dx,0,1,-dy),Image.Resampling.BICUBIC)


class AdaptiveCutout:
    def __init__(self,analysis):
        self.source=Image.open(analysis['rgba']).convert('RGBA')
        self.rig=json.loads(Path(analysis['rig']).read_text('utf-8'))
        self.points=self.rig['joints']; self.array=np.array(self.source)
        self.alpha=self.array[:,:,3]
        self.yy,self.xx=np.mgrid[:1024,:768]
        self._split()

    def p(self,key): return np.asarray(self.points[key][:2],dtype=float)

    def _split(self):
        shoulder,elbow,wrist=(self.p('right_'+name) for name in ('shoulder','elbow','wrist'))
        hip,knee,ankle=(self.p('right_'+name) for name in ('hip','knee','ankle'))
        box=self.source.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()
        body_width=box[2]-box[0]
        # Estimate arm radius from the visible outer silhouette rather than fixed coordinates.
        radii=[]
        for t in (.2,.4,.6,.8):
            center=(1-t)*shoulder+t*elbow; row=int(np.clip(center[1],0,1023))
            xs=np.flatnonzero(self.alpha[row]>64)
            if len(xs): radii.append(max(8,center[0]-xs[0]))
        radius=float(np.clip(np.median(radii) if radii else body_width*.15,12,body_width*.26))
        hand_end=wrist+(wrist-elbow)*.70
        distance=np.minimum.reduce([line_distance(self.xx,self.yy,shoulder,elbow),
                                    line_distance(self.xx,self.yy,elbow,wrist),
                                    line_distance(self.xx,self.yy,wrist,hand_end)])
        arm_mask=(distance<radius+5)&(self.yy>=shoulder[1]-radius*.35)&(self.yy<=hand_end[1]+radius*.5)
        arm_mask&=self.alpha>0
        # Body geometry alone includes trousers/blouse behind a bare arm. Use the visible
        # arm's own palette to avoid dragging those background garment patches with it.
        samples=[]
        for a,b in ((shoulder,elbow),(elbow,wrist)):
            for t in (.25,.5,.75):
                center=(1-t)*a+t*b; x,y=np.round(center).astype(int)
                pixels=self.array[max(0,y-2):y+3,max(0,x-2):x+3,:3]
                samples.append(np.median(pixels.reshape(-1,3),axis=0))
        colors=self.array[:,:,:3].astype(float)
        color_distance=np.minimum.reduce([np.linalg.norm(colors-color,axis=2) for color in samples])
        core=arm_mask&(color_distance<80)
        arm_mask=arm_mask&ndimage.binary_dilation(core,iterations=2)
        hand_points=np.asarray(self.rig.get('visible_hand_keypoints',[]),dtype=float)
        if len(hand_points)>=10:
            valid=hand_points[hand_points[:,2]>.25,:2]
            hull=ConvexHull(valid)
            hand_mask=Image.new('L',SIZE)
            ImageDraw.Draw(hand_mask).polygon([tuple(point) for point in valid[hull.vertices]],fill=255)
            hand_mask=np.asarray(hand_mask.filter(ImageFilter.MaxFilter(9)))>0
            arm_mask&=(self.yy<wrist[1]+12)|hand_mask
            bridge=ndimage.binary_closing(arm_mask,iterations=3)
            junction=np.hypot(self.xx-wrist[0],self.yy-wrist[1])<radius*1.1
            arm_mask|=bridge&junction&(self.alpha>0)
            self.hand_extension=float(np.clip((valid[:,1].max()+8-wrist[1])/max(1,wrist[1]-elbow[1]),.35,.85))
            hand_end=wrist+(wrist-elbow)*self.hand_extension
        else:
            self.hand_extension=.7
        # Find garment-to-leg color transition after removing the arm from the measurement.
        thigh=math.dist(hip,knee); lo=int(hip[1]+thigh*.10); hi=int(hip[1]+thigh*.66)
        colors=[]; rows=[]
        for y in range(max(0,lo-8),min(1024,hi+8)):
            xs=np.flatnonzero((self.alpha[y]>220)&~arm_mask[y])
            if len(xs)>8:
                front=xs[-1]; sample=xs[(xs>front-24)&(xs<front-4)]
                if len(sample): colors.append(np.median(self.array[y,sample,:3],axis=0)); rows.append(y)
        self.hem=int(hip[1]+thigh*.36)
        if len(rows)>20:
            colors=ndimage.gaussian_filter1d(np.asarray(colors,dtype=float),2,axis=0)
            differences=np.linalg.norm(colors[8:]-colors[:-8],axis=1)
            candidates=np.flatnonzero(differences>65)
            if len(candidates): self.hem=int(rows[int(candidates[0])+4])
        self.hem=int(np.clip(self.hem,hip[1]+thigh*.10,hip[1]+thigh*.65))
        self.arm=self._part(arm_mask)
        # Recover clothing/skin obscured by the hand from the visible leg on the same row.
        leg_array=self.array.copy(); leg_array[arm_mask,3]=0
        radii=[]
        for y in range(int(min(hand_end[1]+25,knee[1])),int(ankle[1]-20),12):
            t=np.clip((y-hip[1])/max(1,knee[1]-hip[1]),0,1)
            center=(1-t)*hip[0]+t*knee[0]
            xs=np.flatnonzero((self.alpha[y]>200)&~arm_mask[y])
            if len(xs): radii.append(max(center-xs[0],xs[-1]-center))
        leg_radius=float(np.clip(np.median(radii) if radii else body_width*.2,20,body_width*.33))
        for y in range(self.hem-12,min(1023,int(hand_end[1]+20))):
            t=np.clip((y-hip[1])/max(1,knee[1]-hip[1]),0,1); center=(1-t)*hip[0]+t*knee[0]
            available=np.flatnonzero(leg_array[y,:,3]>200)
            needed=np.flatnonzero(arm_mask[y]&(np.abs(self.xx[y]-center)<leg_radius))
            if len(available):
                for x in needed:
                    nearest=available[np.argmin(np.abs(available-x))]
                    leg_array[y,x,:3]=self.array[y,nearest,:3]; leg_array[y,x,3]=255
        # Extend the first visible leg color underneath the garment. Otherwise cloth pixels
        # from above the hem become floating dark strips when the thigh rotates.
        sample_y=min(1023,self.hem+12)
        sample_xs=np.flatnonzero((leg_array[sample_y,:,3]>200)&~arm_mask[sample_y])
        if len(sample_xs):
            color=np.median(leg_array[sample_y,sample_xs,:3],axis=0)
            for y in range(self.hem-12,self.hem+2):
                center=hip[0]+(knee[0]-hip[0])*np.clip((y-hip[1])/max(1,knee[1]-hip[1]),0,1)
                span=np.abs(self.xx[y]-center)<leg_radius
                leg_array[y,span,:3]=color; leg_array[y,span,3]=255
        leg_mask=self.yy>=self.hem-12
        limb=leg_array.copy(); limb[~(leg_mask&(self.yy<=ankle[1]+12)),3]=0; self.leg=Image.fromarray(limb)
        shoe=leg_array.copy(); shoe[~(leg_mask&(self.yy>=ankle[1]-8)),3]=0; self.shoe=Image.fromarray(shoe)
        body=self.array.copy(); body[(self.yy>self.hem+3)|arm_mask,3]=0
        # Reconstruct only the part of torso hidden by the arm, sampling the actual garment.
        for y in range(int(shoulder[1]),min(1023,self.hem+4)):
            t=np.clip((y-shoulder[1])/max(1,hip[1]-shoulder[1]),0,1)
            back=(1-t)*(shoulder[0]+radius*.2)+t*(hip[0]-body_width*.23)
            available=np.flatnonzero((body[y,:,3]>200)&(self.xx[y]>back))
            needed=np.flatnonzero(arm_mask[y]&(self.xx[y]>=back))
            if len(available) and len(needed):
                needed=needed[needed<available[-1]]
                interior=available[ndimage.distance_transform_edt(~arm_mask[y])[available]>4]
                sample=interior if len(interior)>3 else available
                color=np.median(self.array[y,sample,:3],axis=0)
                for x in needed:
                    # Median sampling avoids stretching a black outline across the torso.
                    body[y,x,:3]=color; body[y,x,3]=255
        self.body=Image.fromarray(body)
        self.arm_source=[shoulder-(elbow-shoulder)*.15,shoulder,elbow,wrist,hand_end]
        self.leg_source=[hip,knee,ankle]
        self.metadata={'garment_hem_y':self.hem,'arm_radius':radius,'leg_radius':leg_radius,'layers':'continuous_mesh_source_rgb',
                       'occluded_side':'estimated_from_visible_side','color_patches':'sampled_from_reference'}

    def _part(self,mask):
        out=self.array.copy(); out[:,:,3]=np.where(mask,out[:,:,3],0); return Image.fromarray(out)

    def render(self,rig):
        joints=rig['joints']; point=lambda name:np.asarray(joints[name][:2])
        canvas=Image.new('RGBA',SIZE); repair=Image.new('L',SIZE)
        repair_array=np.zeros((1024,768),dtype=np.uint8)
        legs=[]; arms=[]
        for side in ('left','right'):
            shoulder,elbow,wrist=(point(side+'_'+name) for name in ('shoulder','elbow','wrist'))
            hand_end=wrist+(wrist-elbow)*self.hand_extension
            arms.append(mesh_warp(self.arm,self.arm_source,[shoulder-(elbow-shoulder)*.15,shoulder,elbow,wrist,hand_end],width=70))
            hip,knee,ankle=(point(side+'_'+name) for name in ('hip','knee','ankle'))
            limb=mesh_warp(self.leg,self.leg_source,[hip,knee,ankle],width=75)
            shoe=translated(self.shoe,ankle[0]-self.leg_source[-1][0],ankle[1]-self.leg_source[-1][1])
            limb.alpha_composite(shoe); legs.append(limb)
            for center,radius in ((elbow,15),(knee,19),(shoulder,17)):
                disk=np.hypot(self.xx-center[0],self.yy-center[1])<radius
                repair_array[disk]=255
        canvas.alpha_composite(arms[0]); canvas.alpha_composite(legs[0]); canvas.alpha_composite(legs[1])
        bob=rig.get('bob',0)
        canvas.alpha_composite(translated(self.body,0,bob)); canvas.alpha_composite(arms[1])
        self.last_rgba=canvas
        alpha=canvas.getchannel('A')
        repair=Image.fromarray(repair_array).filter(ImageFilter.GaussianBlur(3))
        repair=ImageChops.multiply(repair,alpha)
        # Workflows see an opaque backdrop; final pixels keep this single tracked alpha.
        return opaque_reference(canvas),alpha,repair


def refine_preserving_color(raw,guide,alpha,repair,base_rgba=None):
    source=np.asarray((base_rgba or guide).convert('RGB'),dtype=np.float32)
    conditioning=np.asarray(guide.convert('RGB'),dtype=np.float32)
    generated=np.asarray(raw.convert('RGB').resize(SIZE),dtype=np.float32)
    weight=np.asarray(repair,dtype=np.float32)[:,:,None]/255
    # AI adds local seam detail; it cannot replace the reference palette or erase a limb.
    out=np.uint8(np.clip(source+np.clip(generated-conditioning,-16,16)*weight,0,255))
    output=Image.fromarray(out).convert('RGBA'); output.putalpha(alpha)
    return output,{'max_rgb_change':int(np.abs(out.astype(np.int16)-source).max()),
                   'opaque_pixels':int((np.asarray(alpha)>250).sum()),'color_policy':'bounded_joint_detail'}
