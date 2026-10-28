import unittest
import numpy as np
from PIL import Image,ImageDraw
from aipictures.character_profile import rig_document
from aipictures.reference_color import repair_reference_hair


class ReferenceColorTests(unittest.TestCase):
    def setUp(self):
        self.reference=Image.new('RGBA',(768,1024)); d=ImageDraw.Draw(self.reference)
        d.ellipse((330,80,460,240),fill=(62,43,82,255))
        d.rectangle((440,155,468,235),fill=(240,210,180,255)); d.rectangle((448,170,453,176),fill=(40,100,40,255))
        d.line((400,240,400,970),fill=(45,42,46,255),width=75)

    def test_green_cast_is_fixed_with_identical_alpha_body_and_eye(self):
        target=self.reference.copy(); array=np.array(target)
        region=np.all(array[:,:,:3]==[62,43,82],axis=2); array[region,:3]=[25,45,40]; target=Image.fromarray(array)
        result,report=repair_reference_hair(target,self.reference,rig_document(),rig_document())
        self.assertGreater(report['changed_pixels'],1000)
        self.assertGreater(result.getpixel((380,130))[2],result.getpixel((380,130))[1])
        self.assertEqual(result.getpixel((450,173)),target.getpixel((450,173)))
        self.assertTrue(np.array_equal(np.asarray(result)[300:],np.asarray(target)[300:]))
        self.assertTrue(np.array_equal(np.asarray(result)[:,:,3],np.asarray(target)[:,:,3]))

    def test_identical_reference_does_not_get_recolored(self):
        result,report=repair_reference_hair(self.reference,self.reference,rig_document(),rig_document())
        self.assertEqual(report['changed_pixels'],0); self.assertTrue(np.array_equal(result,self.reference))

    def test_non_blue_violet_reference_skips_guard(self):
        target=Image.new('RGBA',(768,1024)); ImageDraw.Draw(target).ellipse((330,80,460,240),fill=(30,90,40,255))
        ImageDraw.Draw(target).line((400,240,400,970),fill=(40,40,40,255),width=60)
        result,report=repair_reference_hair(target,target.copy(),rig_document(),rig_document())
        self.assertEqual(report['reason'],'not_violet_blue_reference_hair')
        self.assertTrue(np.array_equal(result,target))


if __name__=='__main__': unittest.main()
