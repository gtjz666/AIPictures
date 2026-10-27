import math
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from aipictures.action_intent import parse_intent
from aipictures.walk_cycle import walk_rig, frame_workflow, export_sequence, SIZE
from aipictures.character_profile import JOINTS, JOINT_NAMES


class WalkTests(unittest.TestCase):
    def test_chinese_negation_and_specific_actions(self):
        intent=parse_intent('不要站立，而是向左走路，保持一致')
        self.assertEqual(intent.action,'walk'); self.assertEqual(intent.direction,'left')
        self.assertIn('stand',intent.negated); self.assertNotIn('standing',intent.english)
        self.assertIsNone(parse_intent('不要走路').action)
        self.assertEqual(parse_intent('向前伸手').action,'reach')
        self.assertEqual(parse_intent('向前伸手，然后站立').action,'stand')
        self.assertIn('walk',parse_intent('不走路').negated)
        self.assertEqual(parse_intent('原地慢走动画').pace,'slow')
        self.assertEqual(parse_intent('换成红色外套').unmatched,'换成红色外套')

    def test_bone_lengths_ground_contact_and_loop(self):
        for pace in ('slow','normal','fast'):
            for i in range(64):
                rig=walk_rig(i/64,pace); p=rig['joints']
                for a,b in [(8,9),(9,10),(11,12),(12,13),(2,3),(3,4)]:
                    self.assertAlmostEqual(math.dist(p[JOINT_NAMES[a]][:2],p[JOINT_NAMES[b]][:2]),
                                           math.dist(JOINTS[a][:2],JOINTS[b][:2]),places=5)
                self.assertTrue(any(abs(p[JOINT_NAMES[a]][1]-910)<.001 for a in (10,13)))
                for x,y,_ in p.values(): self.assertTrue(0<=x<768 and 0<=y<1024)
        self.assertEqual(walk_rig(0)['joints'],walk_rig(1)['joints'])
        # Temporal seam is the same phase spacing as all the other frames.
        self.assertNotEqual(walk_rig(0)['joints'],walk_rig(7/8)['joints'])

    def test_frame_workflow_keeps_three_inputs_separate(self):
        graph=frame_workflow('identity','pose','guide',17,'walking','model')
        self.assertEqual(graph['8']['inputs']['image'],'identity')
        self.assertEqual(graph['21']['inputs']['image'],'pose')
        self.assertEqual(graph['30']['inputs']['image'],'guide')
        self.assertEqual(graph['5']['inputs']['latent_image'],['31',0])
        self.assertEqual(graph['5']['inputs']['positive'],['22',0])
        self.assertEqual(graph['5']['inputs']['seed'],17)
        changed=frame_workflow('identity','pose','guide',17,'walking','model',negative='watermark, extra fingers')
        self.assertEqual(changed['3']['inputs']['text'],'watermark, extra fingers')
        empty=frame_workflow('identity','pose','guide',17,'walking','model',negative='')
        self.assertEqual(empty['3']['inputs']['text'],'')

    def test_export_order_dimensions_and_gif_frame_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); frames=[]
            for i in range(8):
                path=root/f'frame_{i:03d}.png'; image=Image.new('RGBA',SIZE,(i*30,0,0,255))
                image.paste((0,0,0,0),(0,0,64,64)); image.save(path); frames.append(path)
            metadata=export_sequence(root,frames,8)
            self.assertEqual(metadata['columns'],4)
            with Image.open(root/'sprite_sheet.png') as sheet:
                self.assertEqual(sheet.size,(3072,2048)); self.assertEqual(sheet.getpixel((900,128))[0],30)
                self.assertEqual(sheet.getpixel((0,0))[3],0)
            with Image.open(root/'walk.gif') as gif:
                self.assertEqual(gif.n_frames,8); self.assertEqual(gif.info['loop'],0)
                for i in range(8):
                    gif.seek(i); rgba=gif.convert('RGBA')
                    self.assertEqual(rgba.getpixel((0,0))[3],0)
                    self.assertEqual(rgba.getpixel((200,200))[3],255)


if __name__=='__main__': unittest.main()
