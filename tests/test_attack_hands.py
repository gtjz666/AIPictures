import math
from copy import deepcopy
from aipictures.character_profile import rig_document
from aipictures.motion_clip import make_clip,sample_clip
from aipictures.motion_language import make_custom_clip
from aipictures.pose_condition import hand_points
from aipictures.pose_animation import animation_prompt


def observed_base():
    base=rig_document();w=base['joints']['right_wrist']
    base['visible_hand_keypoints']=[[w[0]+(i%5)*4,w[1]+(i//5)*12,.9] for i in range(21)]
    return base


def test_punch_folded_fingers_follow_each_wrist_and_recover_reference_hand():
    base=observed_base();saved=deepcopy(base);clip=make_clip(base,'a'*64,'attack')
    for side in ('right','left'):
        hit=sample_clip(clip,.4);points=hand_points(hit,base,side);w=hit['joints'][side+'_wrist']
        assert len(points)==21 and math.dist(points[0][:2],w[:2])<1e-6
        assert max(math.dist(p[:2],w[:2]) for p in points)<30
        # Folded fingertips return behind the forward knuckles, rather than extending.
        u=hit['joints'][side+'_elbow'];axis=[(w[i]-u[i])/math.dist(w[:2],u[:2]) for i in (0,1)]
        project=lambda p:sum((p[i]-w[i])*axis[i] for i in (0,1))
        for knuckle,tip in ((6,8),(10,12),(14,16),(18,20)):
            assert project(points[tip])<project(points[knuckle])
        assert hand_points(sample_clip(clip,0),base,side)==hand_points(sample_clip(clip,1),base,side)
    assert base==saved


def test_nonhuman_missing_hand_detection_does_not_invent_fingers():
    base=rig_document();base.pop('visible_hand_keypoints',None)
    assert hand_points(sample_clip(make_clip(base,'a'*64,'attack'),.4),base,'right')==[]


def test_compiled_attack_keeps_primitive_and_clenched_hand_condition():
    base=observed_base();pose=sample_clip(make_custom_clip(base,'a'*64,'基础攻击'),.4)
    assert pose['primitive_action']=='attack' and len(hand_points(pose,base,'right'))==21
    assert 'tightly closed fist' in animation_prompt('',action='attack')
