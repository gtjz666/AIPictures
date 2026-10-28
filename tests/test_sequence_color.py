import unittest
from PIL import Image,ImageDraw
import numpy as np
from aipictures.character_profile import rig_document
from aipictures.motion_clip import make_clip
from aipictures.sequence_color import signature,correction_plan,apply_correction


def subject(pose):
    image=Image.new('RGBA',(768,1024)); d=ImageDraw.Draw(image); p=pose['joints']
    d.line([tuple(p['neck'][:2]),tuple(p['right_hip'][:2])],fill=(145,130,115,255),width=75)
    x,y=p['nose'][:2]; d.ellipse((x-48,y-48,x+25,y+35),fill=(95,80,110,255))
    for side in ('right','left'):
        d.line([tuple(p[side+'_hip'][:2]),tuple(p[side+'_knee'][:2]),tuple(p[side+'_ankle'][:2])],fill=(65,72,85,255),width=38)
    return image


class SequenceColorTests(unittest.TestCase):
    def setUp(self): self.pose=make_clip(rig_document(),'a'*64)['frames'][0]; self.image=subject(self.pose)

    def test_global_exposure_spike_is_reduced_with_identical_alpha(self):
        array=np.array(self.image); original=array.copy(); mask=array[:,:,3]>0
        array[mask,:3]=np.clip((array[mask,:3].astype(float)+12)*1.25-12,0,255).round()
        bright=Image.fromarray(array)
        signatures=[signature(image,self.pose) for image in [self.image,self.image,bright,self.image,self.image]]
        report=correction_plan(signatures)[2]; corrected=np.asarray(apply_correction(bright,report))
        self.assertEqual(report['status'],'corrected')
        self.assertLess(np.abs(corrected[mask,:3].astype(float)-original[mask,:3]).mean(),2)
        self.assertTrue(np.array_equal(corrected[:,:,3],original[:,:,3]))
        self.assertTrue(np.array_equal(corrected[~mask],original[~mask]))

    def test_pose_and_silhouette_changes_alone_do_not_change_colors(self):
        poses=make_clip(rig_document(),'a'*64,'run')['frames']
        reports=correction_plan([signature(subject(pose),pose) for pose in poses])
        self.assertTrue(all(report['status']=='stable' for report in reports),reports)

    def test_local_clothing_change_cannot_recolor_the_entire_character(self):
        changed=self.image.copy(); p=self.pose['joints']; draw=ImageDraw.Draw(changed)
        draw.line([tuple(p['neck'][:2]),tuple(p['right_hip'][:2])],fill=(210,190,170,255),width=70)
        reports=correction_plan([signature(image,self.pose) for image in [self.image]*3+[changed]+[self.image]*2])
        self.assertEqual(reports[3]['gain'],[1.,1.,1.])

    def test_stable_sequence_is_bit_identical(self):
        reports=correction_plan([signature(self.image,self.pose)]*8)
        for report in reports: self.assertTrue(np.array_equal(self.image,apply_correction(self.image,report)))

    def test_red_only_regional_difference_cannot_introduce_green_tint(self):
        base=signature(self.image,self.pose); shifted={key:(dict(value) if isinstance(value,dict) else value) for key,value in base.items()}
        for key in ('head','torso','legs'):
            if key in shifted: shifted[key]['log_rgb']=(np.array(base[key]['log_rgb'])+np.array([.09,0,0])).tolist()
        report=correction_plan([base,base,shifted,base,base])[2]
        self.assertEqual(report['status'],'color_cast_requires_review')
        self.assertEqual(report['gain'],[1.,1.,1.])


if __name__=='__main__': unittest.main()
