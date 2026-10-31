"""Retarget measured human timing/directions to the current character's 2D bone lengths."""
import json
import math
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from .motion_kinematics import arm,lengths,move_upper_and_hips,resting_arm_angles,solve_leg,smooth


@lru_cache(maxsize=2)
def profile(action):
    return json.loads((Path(__file__).parent/'resources/human_motion'/(action+'.json')).read_text('utf-8'))


def values(action,phase):
    frames=profile(action)['frames'];at=max(0.,min(1.,phase))*(len(frames)-1)
    left=min(int(at),len(frames)-1);right=min(left+1,len(frames)-1);f=at-left
    return {key:frames[left][key]*(1-f)+frames[right][key]*f for key in frames[left]}


def clamp(value,lo,hi):return max(lo,min(hi,value))


def foot_target(base,side,dx,roll):
    """Toe stays planted while a positive foot pitch lifts heel and ankle together."""
    p=base['joints'];toe=p[side+'_toe'];ankle=p[side+'_ankle']
    vx,vy=ankle[0]-toe[0],ankle[1]-toe[1]
    return [toe[0]+dx+vx*math.cos(roll)-vy*math.sin(roll),
            toe[1]+vx*math.sin(roll)+vy*math.cos(roll),1]


def pose_from_capture(base,phase,action):
    rig=deepcopy(base);p=rig['joints'];source=base['joints'];leg=sum(lengths(base,'right'))
    row=values(action,phase);start=values(action,0)
    pelvis=[(source['right_hip'][i]+source['left_hip'][i])/2 for i in (0,1)]
    ref_lean=math.atan2(source['neck'][0]-pelvis[0],pelvis[1]-source['neck'][1])
    envelope=smooth(phase/(.08 if action=='jump' else .13))*smooth((1-phase)/(.10 if action=='jump' else .18))
    desired_lean=clamp(row['lean'],-.12,.50)
    lean=(desired_lean-ref_lean)*envelope
    twist=clamp((row['twist']-start['twist'])*.35,-.05,.05)*leg*envelope
    if action=='jump':
        air=smooth((phase-.22)/.06)*smooth((.74-phase)/.06)
        ground=1-air
        down=clamp(row['down'],0,.22)*leg*ground*envelope
        dx=clamp(row['balance']-start['balance'],-.12,.08)*leg*ground*envelope
    else:
        air=0.;ground=1.
        # The lead/right sole remains the registration anchor. The rear foot steps out.
        dx=(source['right_ankle'][0]-pelvis[0]-.75*row['r_ankle_x']*leg)*envelope
        down=(.035+clamp(row['down'],-.025,.12))*leg*envelope
    move_upper_and_hips(rig,dx,down)
    contacts={};toe_contacts={};rolls={}
    for side,short in (('right','r'),('left','l')):
        if action=='jump':
            shift=0.
            roll=clamp(row[short+'_roll'],0,math.radians(28))*envelope
            if abs(roll)<1e-4:roll=0.
            # Airborne foot pitch is free; supported toe-off preserves the toe anchor.
            roll_air=clamp(row[short+'_roll'],-.4,.6)*envelope
            upper,lower=lengths(base,side);hip=p[side+'_hip']
            a,b=row[short+'_upper_leg'],row[short+'_lower_leg']
            flying=[hip[0]+upper*math.sin(a)+lower*math.sin(b),hip[1]+upper*math.cos(a)+lower*math.cos(b),1]
            grounded=foot_target(base,side,shift,roll)
            ankle=[grounded[i]*(1-air)+flying[i]*air for i in (0,1)]+[1]
            rolls[side]=roll*(1-air)+roll_air*air
            supported=air==0.
        else:
            shift=dx+envelope*(pelvis[0]+.75*row[short+'_ankle_x']*leg-source[side+'_ankle'][0])
            roll=clamp(row[short+'_roll'],0,math.radians(28))*envelope
            if abs(roll)<1e-4:roll=0.
            ankle=foot_target(base,side,shift,roll)
            # A real back-step opens the stance; do not slide two flat feet apart.
            lift=0.
            if side=='left':
                for step_start,step_end in ((.00,.18),(.80,1.0)):
                    t=(phase-step_start)/(step_end-step_start)
                    if 0<t<1:lift=leg*.045*math.sin(math.pi*t)**2
            if lift<.01:lift=0.
            ankle[1]-=lift;rolls[side]=roll;supported=lift<.01
        if action=='jump':
            # Resolve shoe clearance before IK. Clamping only heel/toe afterwards
            # would make the BODY_18 ankle differ from the solved leg endpoint.
            pitch=rolls[side];origin=source[side+'_ankle']
            shoe_depth=max((source[side+'_'+part][0]-origin[0])*math.sin(pitch)+
                (source[side+'_'+part][1]-origin[1])*math.cos(pitch) for part in ('heel','toe'))
            ankle[1]=min(ankle[1],base.get('ground_y',978)-shoe_depth)
        solve_leg(p,base,side,ankle)
        contacts[side]=supported and abs(rolls[side])<1e-4
        toe_contacts[side]=supported and not contacts[side]
        rest_a,rest_b=resting_arm_angles(base,side)
        # Body rotation is applied later; compensate here to retain captured global arm directions.
        a=rest_a*(1-envelope)+row[short+'_upper_arm']*envelope+lean
        b=rest_b*(1-envelope)+row[short+'_lower_arm']*envelope+lean
        arm(p,base,side,a,b)
    rig.update(natural_capture=profile(action)['source']['sample'],capture_lean=lean,capture_twist=twist,
        contacts=contacts,toe_contacts=toe_contacts,foot_angles=rolls)
    if action=='jump':rig.update(game_platformer=True,airborne=.26<phase<.70,jump_crouch=down/leg,
        jump_clearance={'root_lift_limit':0.,'top_margin':40,'boundary_source':'engine_root_motion_not_baked'})
    else:rig.update(attack_ready=envelope,attack_strike=1 if .37<=phase<=.46 else 0,
        hitbox_active=.34<=phase<=.47)
    return rig
