"""Proportion-scaled contact phases and exact-length biped mechanics, without texture warping."""
import math
from copy import deepcopy
from .walk_cycle import knee_ik


def smooth(value):
    value=max(0.,min(1.,value));return value*value*(3-2*value)


def curve(phase, keys):
    for (a,x),(b,y) in zip(keys,keys[1:]):
        if a<=phase<=b:return x+(y-x)*smooth((phase-a)/(b-a))
    return keys[-1][1]


def lengths(base,side):
    p=base['joints']
    return (math.dist(p[side+'_hip'][:2],p[side+'_knee'][:2]),
            math.dist(p[side+'_knee'][:2],p[side+'_ankle'][:2]))


def solve_leg(p,base,side,ankle):
    upper,lower=lengths(base,side);hip=p[side+'_hip']
    dx,dy=ankle[0]-hip[0],ankle[1]-hip[1];distance=math.hypot(dx,dy)
    if distance<1e-6 or min(upper,lower)<1:raise ValueError('腿部比例无效，请调整基准骨骼。')
    reach=max(abs(upper-lower)+.001,min(upper+lower-.001,distance))
    if abs(reach-distance)>.0001:
        hip[:2]=[ankle[0]-dx*reach/distance,ankle[1]-dy*reach/distance]
    p[side+'_ankle']=ankle[:]
    p[side+'_knee']=knee_ik(hip,ankle,upper,lower)


def arm(p,base,side,upper_angle,lower_angle):
    source=base['joints'];shoulder=p[side+'_shoulder']
    upper=math.dist(source[side+'_shoulder'][:2],source[side+'_elbow'][:2])
    lower=math.dist(source[side+'_elbow'][:2],source[side+'_wrist'][:2])
    elbow=[shoulder[0]+upper*math.sin(upper_angle),shoulder[1]+upper*math.cos(upper_angle),1]
    p[side+'_elbow']=elbow
    p[side+'_wrist']=[elbow[0]+lower*math.sin(lower_angle),elbow[1]+lower*math.cos(lower_angle),1]


def resting_arm_angles(base,side):
    source=base['joints'];shoulder,elbow,wrist=(source[side+'_'+part] for part in ('shoulder','elbow','wrist'))
    return (math.atan2(elbow[0]-shoulder[0],elbow[1]-shoulder[1]),
            math.atan2(wrist[0]-elbow[0],wrist[1]-elbow[1]))


def move_upper_and_hips(rig,dx,dy):
    for name,point in rig['joints'].items():
        if not any(part in name for part in ('knee','ankle','heel','toe')):
            point[0]+=dx;point[1]+=dy


def walk_pose(base,phase):
    rig=deepcopy(base);p=rig['joints'];source=base['joints'];leg=sum(lengths(base,'right'))
    # Contact -> compression -> passing -> push, twice per full left/right cycle.
    half=(phase*2)%1
    down=curve(half,((0,.035),(.23,.065),(.58,.035),(.82,.018),(1,.035)))*leg
    move_upper_and_hips(rig,0,down)
    for side,offset in (('right',0),('left',.5)):
        q=(phase+offset)%1;stride=leg*.17
        if q<=.62:
            x=stride*(1-2*q/.62);height=0.
        else:
            t=(q-.62)/.38;x=-stride+2*stride*smooth(t)
            height=leg*.10*math.sin(math.pi*t)**2
        # World-space stance slides backward for an in-place sprite; no heel lift
        # is mistaken for a change in leg length or a second shoe.
        ankle=[source[side+'_ankle'][0]+x,source[side+'_ankle'][1]-height,1]
        solve_leg(p,base,side,ankle)
        swing=-.30*math.cos(math.tau*q)
        arm(p,base,side,swing,swing+.12)
    rig['contacts']={side:(phase+offset)%1<=.62 for side,offset in (('right',0),('left',.5))}
    return rig


RUN_KEYS=((0,32,-5),(.13,35,-28),(.32,-15,-35),(.46,0,-130),(.66,40,-100),(.88,48,-20),(1,32,-5))


def run_angles(phase):
    return tuple(math.radians(curve(phase,[(key[0],key[column]) for key in RUN_KEYS])) for column in (1,2))


def run_pose(base,phase):
    rig=deepcopy(base);p=rig['joints'];source=base['joints'];leg=sum(lengths(base,'right'))
    active=None
    for side,offset in (('right',0),('left',.5)):
        q=(phase+offset)%1
        if q<=.32:active=(side,q);break
    def support_dy(side,q):
        upper,lower=lengths(base,side);a,b=run_angles(q)
        return source[side+'_ankle'][1]-source[side+'_hip'][1]-upper*math.cos(a)-lower*math.cos(b)
    if active:dy=support_dy(*active)
    else:
        q=phase%.5;u=(q-.32)/.18
        start='right' if phase<.5 else 'left';end='left' if phase<.5 else 'right'
        dy=(1-u)*support_dy(start,.32)+u*support_dy(end,0)-min(leg*.04,20)*4*u*(1-u)
    move_upper_and_hips(rig,0,dy)
    for side,offset in (('right',0),('left',.5)):
        q=(phase+offset)%1;upper,lower=lengths(base,side);a,b=run_angles(q);hip=p[side+'_hip']
        knee=[hip[0]+upper*math.sin(a),hip[1]+upper*math.cos(a),1]
        p[side+'_knee']=knee
        p[side+'_ankle']=[knee[0]+lower*math.sin(b),knee[1]+lower*math.cos(b),1]
        swing=-.50*math.cos(math.tau*q)
        arm(p,base,side,swing,swing+1.30)
    rig['contacts']={side:(phase+offset)%1<=.32 for side,offset in (('right',0),('left',.5))}
    return rig


def squat_pose(base,phase):
    rig=deepcopy(base);p=rig['joints'];leg=sum(lengths(base,'right'))
    amount=curve(phase,((0,0),(.08,0),(.42,1),(.58,1),(.90,0),(1,0)))
    move_upper_and_hips(rig,-leg*.15*amount,leg*.31*amount)
    for side in ('right','left'):
        solve_leg(p,base,side,base['joints'][side+'_ankle'])
        angle=amount*.65
        a,b=resting_arm_angles(base,side)
        arm(p,base,side,a*(1-amount)+angle,b*(1-amount)+angle+.10*amount)
    rig.update(squat_amount=amount,contacts={'right':True,'left':True})
    return rig


def jump_pose(base,phase):
    rig=deepcopy(base);p=rig['joints'];source=base['joints'];leg=sum(lengths(base,'right'))
    crouch=curve(phase,((0,0),(.08,.25),(.17,1),(.27,0),(.72,0),(.82,.8),(1,0)))
    air=(phase-.27)/.45 if .27<phase<.72 else None
    headroom=max(0,min(source[name][1] for name in ('nose','right_eye','left_eye'))-55)
    height=min(leg*.22,headroom)
    lift=height*4*air*(1-air) if air is not None else 0.
    move_upper_and_hips(rig,-leg*.10*crouch,leg*.22*crouch-lift)
    hand_raise=curve(phase,((0,0),(.15,-.35),(.32,1),(.50,1),(.76,.15),(1,0)))
    for side in ('right','left'):
        ankle=source[side+'_ankle'][:]
        if air is not None:ankle[1]-=lift+leg*.045*math.sin(math.pi*air)
        solve_leg(p,base,side,ankle)
        a,b=resting_arm_angles(base,side)
        arm(p,base,side,a+hand_raise*1.65,b+hand_raise*1.65-.12*math.sin(math.pi*max(0,hand_raise)))
    rig.update(jump_crouch=crouch,airborne=air is not None,contacts={'right':air is None,'left':air is None})
    return rig
