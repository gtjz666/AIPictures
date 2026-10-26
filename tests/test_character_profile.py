import math
import unittest
from aipictures.character_profile import rig_document, pose_presets, character_workflow, JOINT_NAMES
from aipictures.prompt_binding import bindings


class CharacterPresetTests(unittest.TestCase):
    def test_body18_coordinates_and_version_are_explicit(self):
        rig = rig_document()
        self.assertEqual(rig['schema_version'], 3)
        self.assertEqual(len(rig['joints']), 18)
        self.assertEqual(set(rig['joints']), set(JOINT_NAMES))
        for x, y, confidence in rig['joints'].values():
            self.assertTrue(0 <= x < 768 and 0 <= y < 1024)
            self.assertTrue(0 < confidence <= 1)
        self.assertLess(rig['joints']['left_hip'][2], rig['joints']['right_knee'][2])

    def test_reach_preserves_arm_bone_lengths(self):
        poses = pose_presets()
        a, b = [poses[key]['rig']['joints'] for key in ('stand', 'reach')]
        for start, end in [('right_shoulder','right_elbow'),('right_elbow','right_wrist')]:
            self.assertAlmostEqual(math.dist(a[start][:2],a[end][:2]), math.dist(b[start][:2],b[end][:2]), delta=.1)

    def test_reference_and_pose_are_distinct_workflow_inputs(self):
        baseline = character_workflow('reference.png')
        controlled = character_workflow('reference.png','pose.png')
        self.assertEqual(bindings(baseline)['reference'], ['8'])
        self.assertEqual(bindings(controlled)['reference'], ['8'])
        self.assertEqual(controlled['21']['inputs']['image'],'pose.png')
        self.assertEqual(controlled['5']['inputs']['positive'],['22',0])
        self.assertEqual(baseline['5']['inputs']['denoise'],.3)
        self.assertEqual(controlled['5']['inputs']['denoise'],1.)


if __name__ == '__main__': unittest.main()
