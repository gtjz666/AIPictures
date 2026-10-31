import math
from pathlib import Path
import numpy as np
import pytest
from aipictures.character_profile import rig_document
from aipictures.motion_clip import make_clip,sample_clip,body_pose,with_feet
from aipictures.natural_motion import profile
from aipictures.game_animation import game_metadata
from tools.research_mocap import world_positions


def test_capture_sources_and_retargeted_lengths_are_independent_of_source_actor():
    assert profile('jump')['source']['sample']=='16_05'
    assert profile('attack')['source']['sample']=='14_01'
    base=rig_document()
    # Shorten the character's arms; the capture actor's bone lengths must not leak in.
    for side in ('right','left'):
        p=base['joints'];s=p[side+'_shoulder'];e=p[side+'_elbow'];w=p[side+'_wrist']
        e[:2]=[s[i]+(e[i]-s[i])*.7 for i in (0,1)]
        w[:2]=[e[i]+(w[i]-e[i])*.7 for i in (0,1)]
    for action in ('jump','attack'):
        clip=make_clip(base,'a'*64,action,16)
        for i in range(129):
            p=sample_clip(clip,i/128)['joints'];b=clip['base_rig']['joints']
            for side in ('right','left'):
                for a,z in (('hip','knee'),('knee','ankle'),('shoulder','elbow'),('elbow','wrist')):
                    a,z=side+'_'+a,side+'_'+z
                    assert math.dist(p[a][:2],p[z][:2])==pytest.approx(math.dist(b[a][:2],b[z][:2]),abs=1e-5)


def test_attack_fixed_lead_toe_back_step_and_rear_toe_drive():
    clip=make_clip(rig_document(),'a'*64,'attack');base=clip['base_rig']['joints']
    for i in range(129):
        pose=sample_clip(clip,i/128);p=pose['joints']
        assert p['right_toe'][:2]==pytest.approx(base['right_toe'][:2],abs=1e-5)
        assert max(p[s+'_'+part][1] for s in ('right','left') for part in ('heel','toe'))<=978+1e-5
        standard=body_pose(pose,clip['base_rig'])
        for side in ('right','left'):
            assert standard['joints'][side+'_ankle'][:2]==pytest.approx(p[side+'_ankle'][:2],abs=1e-5)
    for phase in (.08,.9):
        pose=sample_clip(clip,phase)
        assert not pose['contacts']['left'] and not pose['toe_contacts']['left']
        assert pose['joints']['left_toe'][1]<978-2
    hit=sample_clip(clip,.4)
    assert hit['toe_contacts']['left'] and hit['joints']['left_heel'][1]<978-10
    assert hit['joints']['left_toe'][1]==pytest.approx(978)
    assert abs(hit['capture_twist'])>10


def test_jump_loads_and_absorbs_without_baking_flight_and_no_boundary_snap():
    clip=make_clip(rig_document(),'a'*64,'jump');base=clip['base_rig']['joints']
    assert sample_clip(clip,.18)['joints']['right_hip'][1]>base['right_hip'][1]+40
    assert sample_clip(clip,.8)['joints']['right_hip'][1]>base['right_hip'][1]+20
    for phase in (.30,.4,.5,.65):
        pose=sample_clip(clip,phase)
        assert pose['airborne'] and not any(pose['contacts'].values())
        assert pose['joints']['right_hip'][1]==pytest.approx(base['right_hip'][1])
    for action in ('jump','attack'):
        sequence=make_clip(rig_document(),'a'*64,action)
        previous=sample_clip(sequence,0)['joints']
        for i in range(1,129):
            current=sample_clip(sequence,i/128)['joints']
            assert max(math.dist(current[n][:2],previous[n][:2]) for n in current)<45
            previous=current
        assert sample_clip(sequence,1)['joints']==sample_clip(sequence,0)['joints']


def test_v4_replay_and_versioned_game_phases():
    base=rig_document();old=make_clip(base,'a'*64,'jump',revision=4)
    new=make_clip(base,'a'*64,'jump')
    assert 'natural_capture' not in sample_clip(old,.4)
    assert sample_clip(new,.4)['natural_capture']=='16_05'
    frames=[{'phase':i/7} for i in range(8)]
    a=game_metadata('jump',frames,8,4);b=game_metadata('jump',frames,8,5)
    assert a['preview_only']['liftoff']==.14 and b['preview_only']['liftoff']==.26
    assert b['clips']['land']==[5,6,7]
    assert sorted(sum(b['clips'].values(),[]))==list(range(8))
    from aipictures.animation_actions import V4_CLAUSES,ACTIONS
    from aipictures.pose_animation import animation_prompt
    assert V4_CLAUSES['jump'] in animation_prompt('','jump',revision=4)
    assert ACTIONS['jump'][1] in animation_prompt('','jump',revision=5)
    assert 'hinge the hips' not in animation_prompt('','jump',revision=4)
    assert 'hinge the hips' in animation_prompt('','jump',revision=5)
    assert 'drive from the rear toes' in animation_prompt('','attack',revision=5)


def test_asf_channels_and_root_transform(tmp_path):
    asf=tmp_path/'s.asf';amc=tmp_path/'s.amc'
    asf.write_text(':bonedata\nbegin\nname arm\ndirection 0 1 0\nlength 2\naxis 0 0 0 XYZ\ndof rz\nend\n:hierarchy\nbegin\nroot arm\nend\n')
    amc.write_text(':DEGREES\n1\nroot 3 4 5 0 0 0\narm 90\n2\nroot 3 4 5 0 0 90\narm 0\n')
    tracks,_,_=world_positions(asf,amc)
    assert np.allclose(tracks['arm'],[[1,4,5],[1,4,5]])


def test_jump_foot_floor_constraint_does_not_change_body18_ankle_or_bone_lengths():
    base=with_feet(rig_document())
    # Tall/long shoes expose a mismatch if heel/toe are clamped after leg IK.
    for side in ('right','left'):
        ankle=base['joints'][side+'_ankle']
        base['joints'][side+'_heel']=[ankle[0]-25,978,1]
        base['joints'][side+'_toe']=[ankle[0]+100,978,1]
    clip=make_clip(base,'a'*64,'jump')
    for i in range(129):
        pose=sample_clip(clip,i/128);body=body_pose(pose,base)
        for side in ('right','left'):
            name=side+'_ankle'
            assert body['joints'][name][:2]==pytest.approx(pose['joints'][name][:2],abs=1e-5)
            assert max(pose['joints'][side+'_'+part][1] for part in ('heel','toe'))<=978+1e-5
