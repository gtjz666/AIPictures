import json
import tempfile
import threading
import unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch,Mock
from PIL import Image,ImageDraw

from aipictures.character_profile import rig_document,JOINT_NAMES
from aipictures.motion_clip import ACTIONS,FOOT_NAMES,make_clip,sample_clip,validate_clip,body_pose
from aipictures.pose_animation import video_workflow,animation_prompt,bind_model_names,export_frames
from aipictures.motion_reference import silhouette_rig,prepare_motion_reference
from aipictures.reference_analysis import PoseNotApplicable
from aipictures.action_intent import appearance_description,parse_intent


class MotionClipTests(unittest.TestCase):
    def test_all_actions_complete_named_biped_and_independent_feet(self):
        for action in ACTIONS:
            clip=make_clip(rig_document(),'a'*64,action,16)
            self.assertEqual(len(clip['frames']),16)
            for pose in clip['frames']:
                self.assertTrue(set(JOINT_NAMES+list(FOOT_NAMES))<=set(pose['joints']))
            self.assertEqual(sample_clip(clip,0)['joints'],sample_clip(clip,1)['joints'])

    def test_walk_has_opposite_contacts_and_full_period(self):
        clip=make_clip(rig_document(),'a'*64)
        phases=[]
        for i in range(8):
            p=clip['frames'][i]['joints']
            phases.append(p['right_ankle'][0]-p['left_ankle'][0])
        self.assertLess(min(phases),-60); self.assertGreater(max(phases),60)
        self.assertLess(phases[0]*phases[4],0)
        self.assertEqual(clip['frames'][0]['joints'],sample_clip(clip,1)['joints'])

    def test_running_contains_real_flight_and_jump_crouches_then_leaves_ground(self):
        clip=make_clip(rig_document(),'a'*64,'run',16)
        self.assertTrue(any(max(frame['joints'][name][1] for name in FOOT_NAMES)<960 for frame in clip['frames']))
        jump=make_clip(rig_document(),'a'*64,'jump',16)
        hip=jump['base_rig']['joints']['right_hip'][1]
        self.assertTrue(any(frame['joints']['right_hip'][1]>hip+20 for frame in jump['frames']))
        self.assertTrue(any(frame['joints']['right_hip'][1]<hip-40 for frame in jump['frames']))

    def test_joint_edit_interpolates_without_overwriting_other_keys(self):
        clip=make_clip(rig_document(),'a'*64)
        original=deepcopy(clip['frames'][2])
        clip['frames'][1]['joints']['right_wrist'][0]+=40; clip['edited']=True
        self.assertEqual(sample_clip(clip,1/8)['joints']['right_wrist'],clip['frames'][1]['joints']['right_wrist'])
        expected=(clip['frames'][0]['joints']['right_wrist'][0]+clip['frames'][1]['joints']['right_wrist'][0])/2
        self.assertAlmostEqual(sample_clip(clip,1/16)['joints']['right_wrist'][0],expected)
        self.assertEqual(clip['frames'][2],original)

    def test_invalid_frame_or_nan_is_rejected(self):
        clip=make_clip(rig_document(),'a'*64); clip['frames'].pop()
        with self.assertRaises(ValueError): validate_clip(clip)

    def test_foot_edit_changes_derived_ankle_without_nonstandard_colored_landmarks(self):
        clip=make_clip(rig_document(),'a'*64); pose=deepcopy(clip['frames'][0])
        before=body_pose(pose,clip['base_rig'])['joints']['right_ankle']
        pose['joints']['right_heel'][0]+=24; pose['joints']['right_toe'][0]+=24
        after=body_pose(pose,clip['base_rig'])['joints']['right_ankle']
        self.assertAlmostEqual(after[0]-before[0],24)

    def test_nonhuman_estimate_uses_its_own_silhouette_not_a_saved_character(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'mascot.png'
            image=Image.new('RGBA',(180,250)); ImageDraw.Draw(image).ellipse((20,10,160,240),fill='orange'); image.save(source)
            with patch('aipictures.motion_reference.DATA',root),patch('aipictures.motion_reference.prepare_reference',side_effect=PoseNotApplicable('not human')):
                analysis=prepare_motion_reference(source,Mock())
            self.assertEqual(analysis['layout'],'estimated_compact_biped')
            rig=json.loads(Path(analysis['rig']).read_text('utf-8'))
            self.assertEqual(rig['annotation'],'silhouette_estimate')
            self.assertEqual(rig['ground_y'],978)
            for action in ACTIONS: self.assertEqual(len(make_clip(rig,analysis['source_sha256'],action)['frames']),8)

    def test_controlled_export_keeps_entire_period_and_jump_height(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); paths=[]
            for i in range(17):
                path=root/f'raw_{i:03d}.png'; image=Image.new('RGBA',(480,640))
                ImageDraw.Draw(image).rectangle((200,100+i*3,270,300+i*3),fill=(i*10,100,120,255)); image.save(path); paths.append(str(path))
            clip=make_clip(rig_document(),'a'*64,'jump')
            manifest={'frames':[],'source_frame_count':17,'fps':8,'frame_count':8,'canvas':[768,1024]}
            with patch('aipictures.pose_animation.foreground_rgba',side_effect=lambda image,*_,**kw:image.convert('RGBA')) as matte,patch('aipictures.pose_animation.release_session'):
                result=export_frames(root,{'images':paths,'prompt_id':'owned'},manifest,clip,lambda *args:None,threading.Event())
                self.assertTrue(all(call.kwargs.get('anti_alias') is False for call in matte.call_args_list))
            self.assertEqual(manifest['pose_selection']['source_indices'],list(range(0,16,2)))
            self.assertTrue(Path(result['gif']).name=='jump.gif' and Path(result['gif']).is_file())
            boxes=[]
            for name in result['frames']:
                with Image.open(name) as image: boxes.append(image.getbbox())
            self.assertGreater(boxes[-1][1]-boxes[0][1],40)
            # The pixel route must receive native resolution before old resizing
            # and color repair, with independent per-frame provenance.
            for i,entry in enumerate(manifest['frames']):
                with Image.open(root/entry['native_matte']) as native:
                    self.assertEqual(native.size,(480,640))
                    self.assertEqual(native.getpixel((210,110+i*6)),(i*20,100,120,255))
        clip=make_clip(rig_document(),'a'*64); clip['frames'][0]['joints']['right_ankle'][0]=float('nan')
        with self.assertRaises(ValueError): validate_clip(clip)

    def test_pose_graph_really_consumes_every_control_frame_and_trims_reference(self):
        names=[f'pose_{i}.png' for i in range(17)]
        graph=video_workflow('ref.png',names,'walk','extra feet',7)
        self.assertEqual(graph['8']['class_type'],'WanAnimateToVideo')
        def leaves(link):
            node=graph[link[0]]
            if node['class_type']=='LoadImage': return [node['inputs']['image']]
            return leaves(node['inputs']['image1'])+leaves(node['inputs']['image2'])
        self.assertEqual(leaves(graph['8']['inputs']['pose_video']),names)
        self.assertEqual(graph['12']['inputs']['trim_amount'],['8',3])
        self.assertEqual(graph['13']['inputs']['samples'],['12',0])
        self.assertEqual(graph['11']['inputs']['cfg'],1)
        self.assertNotIn('acceleration',graph)

    def test_action_selection_owns_text_and_appearance_macro_is_removed_for_character(self):
        for action in ACTIONS:
            text=animation_prompt('站立，蓝色头发',action)
            self.assertIn(ACTIONS[action][1],text)
            positive='参考图中的同一角色，'+ACTIONS[action][1]
            self.assertNotIn(ACTIONS[action][1],appearance_description(positive))
            self.assertEqual(parse_intent(positive).action,action)

    def test_negative_exclusions_are_written_into_cfg1_generation_requirements(self):
        text=animation_prompt('参考角色','run',True,'颜色缺失，鞋子重影，机械翅膀')
        self.assertIn('参考配色完整统一',text)
        self.assertIn('鞋底轮廓清晰',text)
        self.assertIn('避免出现机械翅膀',text)
        self.assertIn('避免出现帽子',animation_prompt('参考角色','walk',True,'不要出现帽子'))


if __name__=='__main__': unittest.main()
