import math
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from aipictures.background import foreground_rgba
from aipictures.reference_analysis import clean_foreground,normalize_reference,aligned_rig,REFERENCE_POSITIVE
from aipictures.character_profile import rig_document,JOINT_NAMES
from aipictures.walk_cycle import walk_rig
from aipictures.skin_warp import refine_preserving_color


class ReferenceAnalysisTests(unittest.TestCase):
    def test_existing_transparent_colors_and_alpha_survive_without_resegmentation(self):
        image=Image.new('RGBA',(64,64),(0,0,0,0))
        image.paste((39,23,60,255),(10,10,54,54)); image.putpixel((10,20),(180,70,90,128))
        with patch('aipictures.background.session',side_effect=AssertionError('no inference needed')):
            result=foreground_rgba(image,threading.Event())
        self.assertEqual(result.tobytes(),image.tobytes())

    def test_segmentation_applies_alpha_without_dimming_rgb(self):
        image=Image.new('RGB',(32,32),(180,70,90)); mask=Image.new('L',(32,32),128)
        with patch.dict(sys.modules,{'rembg':SimpleNamespace(remove=lambda *a,**kw:mask)}),patch('aipictures.background.session',return_value=object()):
            result=foreground_rgba(image,threading.Event())
        self.assertEqual(result.getpixel((10,10)),(180,70,90,128))

    def test_normalization_ignores_transparent_noise_and_keeps_aspect(self):
        image=Image.new('RGBA',(300,600),(0,0,0,0)); image.paste((90,40,130,255),(100,30,200,570))
        image.putpixel((1,1),(200,0,0,2))
        output,meta=normalize_reference(image)
        self.assertEqual(output.size,(768,1024)); self.assertEqual(meta['source_bbox'],[100,30,200,570])
        bbox=output.getchannel('A').point(lambda a:255 if a>200 else 0).getbbox()
        self.assertAlmostEqual((bbox[2]-bbox[0])/(bbox[3]-bbox[1]),100/540,delta=.01)
        self.assertEqual(output.getpixel((384,500))[:3],(90,40,130))

    def test_joint_detail_cannot_wash_out_or_erase_a_limb(self):
        guide=Image.new('RGB',(768,1024),(190,90,45)); raw=Image.new('RGB',guide.size,'white')
        alpha=Image.new('L',guide.size,255); mask=Image.new('L',guide.size,255)
        output,quality=refine_preserving_color(raw,guide,alpha,mask)
        self.assertLessEqual(quality['max_rgb_change'],16)
        self.assertEqual(output.getpixel((400,600))[3],255)
        self.assertEqual(output.getpixel((400,600))[:3],(206,106,61))
        # Transparent edge RGB is not pre-composited with the viewer backdrop.
        base=Image.new('RGBA',guide.size,(30,10,90,128))
        zero=Image.new('L',guide.size,0)
        output,_=refine_preserving_color(raw,guide,base.getchannel('A'),zero,base)
        self.assertEqual(output.getpixel((0,0)),(30,10,90,128))

    def test_retargeted_cycle_preserves_measured_bone_lengths(self):
        base=rig_document()
        for point in base['joints'].values(): point[0]=384+(point[0]-384)*.85; point[1]=60+(point[1]-35)*.96
        for near,far in ((2,5),(3,6),(4,7),(8,11),(9,12),(10,13)):
            base['joints'][JOINT_NAMES[far]]=base['joints'][JOINT_NAMES[near]][:]
            base['joints'][JOINT_NAMES[far]][0]+=12
        for pace in ('slow','normal','fast'):
            for frame in range(64):
                rig=walk_rig(frame/64,pace,base)
                for a,b in ((2,3),(3,4),(8,9),(9,10),(11,12),(12,13)):
                    names=(JOINT_NAMES[a],JOINT_NAMES[b])
                    expected=math.dist(base['joints'][names[0]][:2],base['joints'][names[1]][:2])
                    actual=math.dist(rig['joints'][names[0]][:2],rig['joints'][names[1]][:2])
                    self.assertAlmostEqual(expected,actual,places=5)
        self.assertNotIn('navy-blue bob',REFERENCE_POSITIVE)


if __name__=='__main__': unittest.main()
