import math
import pytest
from aipictures.animation_actions import ACTIONS,ONE_SHOT_ACTIONS,output_indices
from aipictures.character_profile import rig_document
from aipictures.motion_clip import make_clip,sample_clip,FOOT_NAMES,with_visual_bounds


@pytest.mark.parametrize('action',ACTIONS)
def test_dense_samples_keep_bone_lengths_and_contacts(action):
    clip=make_clip(rig_document(),'a'*64,action)
    base=clip['base_rig']['joints']
    for index in range(129):
        pose=sample_clip(clip,index/128);p=pose['joints']
        for side in ('right','left'):
            for a,b in (('hip','knee'),('knee','ankle'),('shoulder','elbow'),('elbow','wrist')):
                assert math.dist(p[side+'_'+a][:2],p[side+'_'+b][:2])==pytest.approx(
                    math.dist(base[side+'_'+a][:2],base[side+'_'+b][:2]),abs=1e-5)
            if pose.get('contacts',{}).get(side):
                assert p[side+'_ankle'][1]==pytest.approx(base[side+'_ankle'][1],abs=1e-5)
        assert all(math.isfinite(v) for point in p.values() for v in point)


def test_squat_keeps_feet_down_and_has_depth_hold_and_complete_recovery():
    clip=make_clip(rig_document(),'a'*64,'squat')
    assert not clip['loop'] and 'reach' not in ACTIONS
    source=clip['base_rig']['joints'];low=sample_clip(clip,.5)['joints']
    assert low['right_hip'][1]>source['right_hip'][1]+80
    assert low['right_hip'][0]<source['right_hip'][0]-30
    for t in (0,.2,.45,.55,.8,1):
        p=sample_clip(clip,t)['joints']
        for name in FOOT_NAMES+('right_ankle','left_ankle'):
            assert p[name]==pytest.approx(source[name],abs=1e-5)
    assert sample_clip(clip,.45)['joints']==sample_clip(clip,.55)['joints']
    assert sample_clip(clip,1)['stage']=='恢复站立'
    assert output_indices('squat',8,33)[-1]==32
    assert clip['frames'][0]['joints']==clip['frames'][-1]['joints']


def test_walk_has_support_throughout_and_run_has_two_flights():
    walking=make_clip(rig_document(),'a'*64,'walk');running=make_clip(rig_document(),'a'*64,'run')
    for index in range(128):assert any(sample_clip(walking,index/128)['contacts'].values())
    for phase in (.4,.9):assert not any(sample_clip(running,phase)['contacts'].values())
    for phase in (.1,.6):assert any(sample_clip(running,phase)['contacts'].values())


def test_old_unedited_motion_replays_saved_keys_instead_of_new_curves():
    clip=make_clip(rig_document(),'a'*64,'run');clip['generator_version']=2
    clip['frames'][0]['joints']['right_wrist'][0]+=25
    assert sample_clip(clip,0)['joints']==clip['frames'][0]['joints']
    assert sample_clip(clip,1/8)['joints']==clip['frames'][1]['joints']


def test_jump_headroom_uses_hair_boundary_not_eye_height():
    source=rig_document()
    base=with_visual_bounds(source,{'geometry':{'subject_bbox':[290,78,470,978]}})
    assert 'visual_bounds' not in source  # Cached/manual source data remains unchanged.
    clip=make_clip(base,'a'*64,'jump')
    head=('nose','right_eye','left_eye','right_ear','left_ear')
    rest=min(base['joints'][name][1] for name in head)
    for index in range(129):
        pose=sample_clip(clip,index/128)
        estimated_hair_top=78+min(pose['joints'][name][1] for name in head)-rest
        assert estimated_hair_top>=35
        assert pose['jump_clearance']['root_lift_limit']<=38
    assert sample_clip(clip,.5)['joints']['right_ankle'][1]<base['joints']['right_ankle'][1]-10


@pytest.mark.parametrize('action',['walk','idle','run','squat'])
def test_visual_boundary_metadata_does_not_change_other_actions(action):
    base=rig_document()
    bounded=with_visual_bounds(base,{'geometry':{'subject_bbox':[290,78,470,978]}})
    old=make_clip(base,'a'*64,action);new=make_clip(bounded,'a'*64,action)
    for index in range(33):
        assert sample_clip(old,index/32)['joints']==sample_clip(new,index/32)['joints']


def test_visual_bounds_are_mirrored_without_mutating_geometry():
    analysis={'direction':'left','geometry':{'subject_bbox':[120,78,330,978]}}
    base=with_visual_bounds(rig_document(),analysis)
    assert base['visual_bounds']==[438,78,648,978]
    assert analysis['geometry']['subject_bbox']==[120,78,330,978]
