import unittest
from copy import deepcopy
import numpy as np
from PIL import Image,ImageDraw
from aipictures.character_profile import rig_document
from aipictures.motion_clip import with_feet
from aipictures.pose_condition import hand_points,render_condition
from aipictures.hand_quality import repair_reference_hands


class HandConditionTests(unittest.TestCase):
    def setUp(self):
        self.base=with_feet(rig_document()); p=self.base['joints']
        p['right_elbow']=[400,400,1]; p['right_wrist']=[400,500,1]
        p['left_elbow']=[435,400,1]; p['left_wrist']=[435,500,1]
        self.base['visible_hand_keypoints']=[[400,500,1]]+[[400+dx,512+i*12,1] for dx in (-16,-8,0,8,16) for i in range(4)]
        self.reference=Image.new('RGBA',(768,1024)); draw=ImageDraw.Draw(self.reference)
        draw.ellipse((375,490,425,565),fill=(240,210,180,255))
        draw.rectangle((200,400,260,600),fill=(100,40,150,255))

    def test_foreign_yellow_green_on_hand_is_fixed_without_changing_alpha_or_clothes(self):
        target=self.reference.copy(); ImageDraw.Draw(target).rectangle((390,520,408,535),fill=(147,130,74,255))
        repaired,report=repair_reference_hands(target,self.reference,self.base,self.base)
        self.assertGreater(report['changed_pixels'],0)
        self.assertTrue(np.array_equal(np.asarray(repaired)[:,:,3],np.asarray(target)[:,:,3]))
        self.assertTrue(np.array_equal(np.asarray(repaired)[400:600,200:260],np.asarray(target)[400:600,200:260]))
        self.assertGreater(repaired.getpixel((400,525))[2],150)

    def test_reference_colors_and_colored_gloves_are_preserved(self):
        repaired,report=repair_reference_hands(self.reference,self.reference,self.base,self.base)
        self.assertEqual(report['changed_pixels'],0)
        self.assertTrue(np.array_equal(repaired,self.reference))
        glove=Image.new('RGBA',(768,1024)); ImageDraw.Draw(glove).ellipse((375,490,425,565),fill=(30,180,40,255))
        repaired,report=repair_reference_hands(glove,glove,self.base,self.base)
        self.assertEqual(report['reason'],'reference_is_not_skin_hand')

    def test_hand_landmarks_follow_wrist_rotation_and_enter_actual_condition(self):
        pose=deepcopy(self.base); pose['joints']['right_wrist']=[500,400,1]
        points=hand_points(pose,self.base,'right')
        self.assertEqual(points[0][:2],[500,400])
        self.assertAlmostEqual(points[-1][0],548)
        self.assertAlmostEqual(points[-1][1],384)
        rendered=render_condition(pose,self.base)
        self.assertEqual(rendered.size,(480,640))
        self.assertEqual(rendered.getpixel((round(500*480/768),round(400*640/1024))),(0,0,255))


if __name__=='__main__': unittest.main()
