import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from skimage.color import rgb2lab,lab2rgb
from aipictures.palette_consistency import palette_plan,apply_palette
from aipictures.face_reference import reference_face
from aipictures.character_profile import rig_document
from aipictures.pose_animation import video_workflow


class PaletteTests(unittest.TestCase):
    def setUp(self):
        self.pose=rig_document();self.image=Image.new('RGBA',(768,1024))
        draw=ImageDraw.Draw(self.image)
        draw.ellipse((330,75,440,230),fill=(205,130,155,255))
        draw.rectangle((340,230,430,520),fill=(150,40,55,255))
        draw.rectangle((350,520,420,850),fill=(35,32,45,255))
        draw.rectangle((350,850,455,980),fill=(228,226,216,255))
        draw.rectangle((380,320,390,360),fill=(50,150,160,255))

    def process(self,target,reference=None):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'frame.png';target.save(path)
            plan=palette_plan([path],[self.pose],reference or self.image,self.pose)
            return apply_palette(target,self.pose,plan['frames'][0])

    def test_identical_reference_keeps_pixels_exact(self):
        result,report=self.process(self.image)
        self.assertEqual(result.tobytes(),self.image.tobytes())
        self.assertEqual(report['changed_pixels'],0)

    def test_multicolor_exposure_and_desaturation_are_reduced_without_changing_alpha(self):
        source=np.asarray(self.image);mask=source[:,:,3]>0
        pixels=source.copy();lab=rgb2lab(source[mask,:3][None,:,:]/255.)[0]
        lab[:,0]+=12;lab[:,1:]*=.65
        pixels[mask,:3]=np.clip(lab2rgb(lab[None,:,:])[0]*255,0,255).round().astype('uint8')
        target=Image.fromarray(pixels);result,report=self.process(target)
        before=np.linalg.norm(rgb2lab(pixels[mask,:3][None,:,:]/255.)-rgb2lab(source[mask,:3][None,:,:]/255.),axis=2).mean()
        after=np.linalg.norm(rgb2lab(np.asarray(result)[mask,:3][None,:,:]/255.)-rgb2lab(source[mask,:3][None,:,:]/255.),axis=2).mean()
        self.assertLess(after,before*.6,(before,after))
        self.assertTrue(np.array_equal(np.asarray(result)[:,:,3],pixels[:,:,3]))
        self.assertTrue(np.array_equal(np.asarray(result)[~mask],pixels[~mask]))

    def test_transparent_background_cannot_dominate_palette(self):
        original=np.array(self.image);changed=original.copy();changed[changed[:,:,3]==0,:3]=[0,240,0]
        result,report=self.process(Image.fromarray(changed))
        self.assertEqual(result.tobytes(),Image.fromarray(changed).tobytes())

    def test_shading_gradients_are_not_reduced_to_palette_prototypes(self):
        pixels=np.array(self.image)
        for row in range(230,520):
            pixels[row,340:431,:3]=[120+row//8,20+(row-230)//3,40+(row-230)//4]
        reference=Image.fromarray(pixels);target=pixels.copy();mask=target[:,:,3]>0
        lab=rgb2lab(target[mask,:3][None,:,:]/255.)[0];lab[:,0]+=8
        target[mask,:3]=np.clip(lab2rgb(lab[None,:,:])[0]*255,0,255).round().astype('uint8')
        result,report=self.process(Image.fromarray(target),reference)
        shades=np.unique(np.asarray(result)[230:520,380,:3],axis=0)
        self.assertGreater(len(shades),150)
        self.assertGreater(report['changed_pixels'],0)

    def test_compact_yellow_creature_and_white_belly_are_not_forced_into_human_colors(self):
        reference=Image.new('RGBA',(768,1024));draw=ImageDraw.Draw(reference)
        draw.ellipse((220,80,560,950),fill=(240,194,48,255))
        draw.ellipse((380,400,540,820),fill=(246,229,185,255))
        target=reference.copy();pixels=np.array(target);mask=pixels[:,:,3]>0
        pixels[mask,:3]=np.clip(pixels[mask,:3].astype(float)*.84,0,255).round().astype('uint8')
        result,report=self.process(Image.fromarray(pixels),reference)
        before=np.abs(pixels[mask,:3].astype(float)-np.asarray(reference)[mask,:3]).mean()
        after=np.abs(np.asarray(result)[mask,:3].astype(float)-np.asarray(reference)[mask,:3]).mean()
        self.assertLess(after,before*.6)
        self.assertTrue(np.array_equal(np.asarray(result)[:,:,3],pixels[:,:,3]))

    def test_uncertain_large_color_swap_is_reported_instead_of_forced(self):
        target=self.image.copy();ImageDraw.Draw(target).rectangle((340,230,430,520),fill=(0,240,30,255))
        result,report=self.process(target)
        self.assertTrue(report['requires_review'])
        self.assertTrue(np.array_equal(np.asarray(result)[:,:,3],np.asarray(target)[:,:,3]))

    def test_reference_face_branch_is_connected_to_every_condition_frame(self):
        face,report=reference_face(self.image,self.pose)
        self.assertTrue(report['used']);self.assertEqual(face.size,(512,512))
        graph=video_workflow('reference.png',['pose']*17,'walk','',1,face='reference-face.png')
        self.assertEqual(graph['8']['inputs']['face_video'],['face_repeat',0])
        self.assertEqual(graph['face_repeat']['inputs']['amount'],17)
        self.assertEqual(graph['face']['inputs']['image'],'reference-face.png')

    def test_estimated_nonhuman_face_is_not_forced_into_human_face_condition(self):
        self.pose['annotation']='silhouette_estimate'
        face,report=reference_face(self.image,self.pose)
        self.assertIsNone(face);self.assertFalse(report['used'])


if __name__=='__main__':unittest.main()
