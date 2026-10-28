import unittest
import numpy as np
from PIL import Image,ImageDraw
from aipictures.character_profile import rig_document
from aipictures.motion_clip import with_feet
from aipictures.foot_quality import repair_light_footwear


class FootQualityTests(unittest.TestCase):
    def setUp(self):
        self.rig=with_feet(rig_document())
        self.reference=Image.new('RGBA',(768,1024))
        draw=ImageDraw.Draw(self.reference)
        for side in ('right','left'):
            x,y=self.rig['joints'][side+'_ankle'][:2]
            draw.rectangle((x-18,y-65,x+25,y+20),fill=(235,232,229,255))

    def test_small_blue_leak_is_removed_with_identical_alpha_and_outside_pixels(self):
        target=self.reference.copy(); draw=ImageDraw.Draw(target)
        x,y=map(int,self.rig['joints']['right_ankle'][:2])
        draw.rectangle((x-6,y-30,x+5,y-20),fill=(30,60,210,255))
        draw.rectangle((50,50,70,70),fill=(30,60,210,180))
        repaired,report=repair_light_footwear(target,self.reference,self.rig,self.rig)
        before=np.asarray(target); after=np.asarray(repaired)
        self.assertGreater(report['changed_pixels'],0)
        self.assertTrue(np.array_equal(before[:,:,3],after[:,:,3]))
        self.assertTrue(np.array_equal(before[:100],after[:100]))
        changed=np.any(before!=after,axis=2)
        self.assertEqual(changed.sum(),report['changed_pixels'])
        self.assertGreater(repaired.getpixel((x,y-25))[0],200)

    def test_genuine_blue_reference_footwear_is_untouched(self):
        source=self.reference.copy(); x,y=map(int,self.rig['joints']['right_ankle'][:2])
        ImageDraw.Draw(source).rectangle((x-12,y-40,x+12,y),fill=(20,40,200,255))
        repaired,report=repair_light_footwear(source,source,self.rig,self.rig)
        self.assertEqual(report['reason'],'reference_contains_blue_footwear')
        self.assertTrue(np.array_equal(source,repaired))

    def test_dark_footwear_is_untouched(self):
        source=Image.new('RGBA',(768,1024),(30,30,30,255))
        repaired,report=repair_light_footwear(source,source,self.rig,self.rig)
        self.assertEqual(report['reason'],'not_light_reference_footwear')
        self.assertTrue(np.array_equal(source,repaired))

    def test_dark_blue_leak_on_white_boot_is_also_repaired(self):
        target=self.reference.copy(); x,y=map(int,self.rig['joints']['right_ankle'][:2])
        ImageDraw.Draw(target).rectangle((x-6,y-30,x+5,y-20),fill=(75,78,110,255))
        repaired,report=repair_light_footwear(target,self.reference,self.rig,self.rig)
        self.assertGreater(report['changed_pixels'],0)
        self.assertGreater(repaired.getpixel((x,y-25))[0],200)


if __name__=='__main__': unittest.main()
