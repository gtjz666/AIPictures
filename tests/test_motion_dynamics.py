import math
import unittest
from aipictures.character_profile import rig_document
from aipictures.motion_clip import make_clip,sample_clip


class MotionDynamicsTests(unittest.TestCase):
    def test_body_breathes_and_leans_in_all_actions(self):
        for action in ('walk','run','idle','jump','squat'):
            clip=make_clip(rig_document(),'a'*64,action,16)
            necks=[frame['joints']['neck'][:2] for frame in clip['frames']]
            self.assertGreater(max(p[0] for p in necks)-min(p[0] for p in necks),1,action)
            if action!='squat': self.assertGreater(max(p[1] for p in necks)-min(p[1] for p in necks),1,action)
            self.assertEqual(sample_clip(clip,0)['joints'],sample_clip(clip,1)['joints'])

    def test_leg_lengths_survive_weight_shift_and_foot_grounding(self):
        base=rig_document()
        for action in ('walk','run','idle','jump','squat'):
            clip=make_clip(base,'a'*64,action,16)
            for frame in clip['frames']:
                for side in ('right','left'):
                    for a,b in (('hip','knee'),('knee','ankle'),('shoulder','elbow'),('elbow','wrist')):
                        length=lambda rig:math.dist(rig['joints'][side+'_'+a][:2],rig['joints'][side+'_'+b][:2])
                        self.assertAlmostEqual(length(frame),length(base),places=3,msg=action)
            if action in ('idle','squat'):
                for frame in clip['frames']:
                    for side in ('right','left'):
                        self.assertEqual(frame['joints'][side+'_ankle'],clip['base_rig']['joints'][side+'_ankle'])


if __name__=='__main__': unittest.main()
