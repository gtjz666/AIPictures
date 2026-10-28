"""Native-resolution DWPose-style body/hand conditioning, separate from editor colors."""
import colorsys
import math
from PIL import Image,ImageDraw,ImageColor
from .character_profile import JOINT_NAMES,LIMBS,COLORS

HAND_EDGES=tuple((root+i,root+i+1) if i else (0,root+1)
    for root in (0,4,8,12,16) for i in range(4))


def hand_points(rig,base,side):
    template=base.get('visible_hand_keypoints')
    if not template or sum(point[2]>.25 for point in template)<10: return []
    source=base['joints']; target=rig['joints']
    a=source['right_elbow']; b=source['right_wrist']; c=target[side+'_elbow']; d=target[side+'_wrist']
    angle=math.atan2(d[1]-c[1],d[0]-c[0])-math.atan2(b[1]-a[1],b[0]-a[0])
    origin=template[0]; points=[]
    for x,y,score in template:
        dx,dy=x-origin[0],y-origin[1]
        points.append([d[0]+dx*math.cos(angle)-dy*math.sin(angle),d[1]+dx*math.sin(angle)+dy*math.cos(angle),score])
    return points


def render_condition(rig,base,size=(480,640)):
    image=Image.new('RGB',size,'black'); draw=ImageDraw.Draw(image)
    sx,sy=size[0]/768,size[1]/1024
    points=[[rig['joints'][name][0]*sx,rig['joints'][name][1]*sy,rig['joints'][name][2]] for name in JOINT_NAMES]
    # The DWPose renderer uses dimmer elliptical limbs and full-color joint dots.
    # Draw directly at the inference resolution so dots/sticks retain its pixel scale.
    for i,(a,b) in enumerate(LIMBS):
        pa,pb=points[a],points[b]
        if min(pa[2],pb[2])<=.2: continue
        dx,dy=pb[0]-pa[0],pb[1]-pa[1]; length=math.hypot(dx,dy)
        if length<.01: continue
        ux,uy=dx/length,dy/length; cx,cy=(pa[0]+pb[0])/2,(pa[1]+pb[1])/2
        polygon=[(cx+ux*length*.5*math.cos(t)-uy*4*math.sin(t),cy+uy*length*.5*math.cos(t)+ux*4*math.sin(t))
            for t in (j*math.tau/90 for j in range(90))]
        draw.polygon(polygon,fill=tuple(int(c*.6) for c in ImageColor.getrgb(COLORS[i])))
    for point,color in zip(points,COLORS):
        x,y,confidence=point
        if confidence>.2: draw.ellipse((x-4,y-4,x+4,y+4),fill=color)
    for side in ('left','right'):
        hand=[[x*sx,y*sy,score] for x,y,score in hand_points(rig,base,side)]
        if not hand: continue
        for index,(a,b) in enumerate(HAND_EDGES):
            if min(hand[a][2],hand[b][2])<=.25: continue
            color=tuple(round(channel*255) for channel in colorsys.hsv_to_rgb(index/20,1,1))
            draw.line((*hand[a][:2],*hand[b][:2]),fill=color,width=2)
        for x,y,score in hand:
            if score>.25: draw.ellipse((x-3,y-3,x+3,y+3),fill=(0,0,255))
    return image
