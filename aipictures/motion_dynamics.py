"""Small action-specific weight shifts and torso follow-through, with grounded leg IK."""
import math
from .walk_cycle import knee_ik

HEAD=('nose','right_eye','left_eye','right_ear','left_ear')


def rotate(point,pivot,angle):
    x,y=point[0]-pivot[0],point[1]-pivot[1]
    point[:2]=[pivot[0]+x*math.cos(angle)-y*math.sin(angle),pivot[1]+x*math.sin(angle)+y*math.cos(angle)]


def enrich_body(rig,base,phase,action):
    p=rig['joints']; source=base['joints']; t=phase*math.tau
    length=sum(math.dist(source[a][:2],source[b][:2]) for a,b in
        (('right_hip','right_knee'),('right_knee','right_ankle')))
    lean=dx=dy=twist=0.
    if action=='walk':
        # Contact -> down -> passing -> up, twice in a complete left/right cycle.
        dx=length*.004*math.sin(t)
        lean=.025+.010*math.sin(t-.25); twist=length*.004*math.cos(t)
    elif action=='run':
        dx=length*.004*math.sin(t)
        lean=.12+.020*math.sin(t-.25); twist=length*.006*math.cos(t)
    elif action=='idle':
        dy=length*.003*math.sin(t-.15); dx=length*.003*math.sin(t)
        lean=.009*math.sin(t-.35); twist=length*.002*math.sin(t)
    elif action=='squat':
        amount=rig.get('squat_amount',0.)
        lean=.36*amount
    elif action=='jump':
        crouch=rig.get('jump_crouch',0.)
        air=math.sin(math.pi*(phase-.27)/.45) if .27<phase<.72 else 0
        lean=.24*crouch-.035*air
        twist=length*.001*math.sin(t)
    # Hips move over fixed ankle targets; shoulders counter the pelvis instead of
    # moving the entire sprite as one rigid block. Arm bone lengths stay unchanged.
    for side,sign in (('right',1),('left',-1)):
        p[side+'_hip'][0]+=dx-sign*twist*.4
        p[side+'_hip'][1]+=dy
    pelvis=[(p['right_hip'][i]+p['left_hip'][i])/2 for i in (0,1)]
    upper=('neck',)+HEAD+tuple(side+'_'+part for side in ('right','left') for part in ('shoulder','elbow','wrist'))
    for name in upper:
        point=p[name]; point[0]+=dx; point[1]+=dy; rotate(point,pelvis,lean)
    for side,sign in (('right',1),('left',-1)):
        for part in ('shoulder','elbow','wrist'): p[side+'_'+part][0]+=sign*twist
    # The head counter-rotates slightly, rather than snapping with the torso.
    for name in HEAD: rotate(p[name],p['neck'],-lean*.65)
    if action=='idle':
        for side,offset in (('right',0),('left',.3)):
            shoulder=p[side+'_shoulder']; elbow=p[side+'_elbow']; wrist=p[side+'_wrist']
            angle=.018*math.sin(t-.45+offset)
            rotate(elbow,shoulder,angle); rotate(wrist,shoulder,angle)
    for side in ('right','left'):
        hip=p[side+'_hip']; ankle=p[side+'_ankle']
        upper_length=math.dist(source[side+'_hip'][:2],source[side+'_knee'][:2])
        lower_length=math.dist(source[side+'_knee'][:2],source[side+'_ankle'][:2])
        vx,vy=ankle[0]-hip[0],ankle[1]-hip[1]; distance=math.hypot(vx,vy)
        if min(upper_length,lower_length)<1 or distance<1e-6: raise ValueError('腿部骨长不足，请调整基准关节。')
        reach=max(abs(upper_length-lower_length)+.001,min(upper_length+lower_length-.001,distance))
        if abs(reach-distance)>.0001:
            if action in ('idle','squat') or rig.get('contacts',{}).get(side,False):
                hip[:2]=[ankle[0]-vx*reach/distance,ankle[1]-vy*reach/distance]
            else: ankle[:2]=[hip[0]+vx*reach/distance,hip[1]+vy*reach/distance]
        p[side+'_knee']=knee_ik(hip,ankle,upper_length,lower_length)
    rig['body_dynamics']={'version':2,'lean':lean,'weight_shift':[dx,dy]}
    return rig
