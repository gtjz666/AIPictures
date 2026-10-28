import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

from PIL import Image, ImageDraw

from aipictures.action_intent import walk_intent
from aipictures.engine import Cancelled
from aipictures.prompt_text import NEGATIVE, negative_text
from aipictures.temporal_animation import (animation_prompt, video_workflow, prepare_subject,
    loop_indices, generate_temporal, check_video_models, stabilize_frames, release_idle_models,
    initial_character_workflow, finish_sequence)


class TemporalTests(unittest.TestCase):
    def test_selected_walk_overrides_standing_reference_description(self):
        for text in ('', '人物自然站立，侧视，全身', '伸手，向左，保持一致', '不要走路，只站立'):
            intent=walk_intent(text)
            self.assertEqual(intent.action,'walk')
            self.assertIn('walking in place',intent.english)
            self.assertNotIn('standing still upright',intent.english)
        self.assertEqual(walk_intent('侧视，面朝左方').direction,'left')
        self.assertIn('保持参考图朝向',animation_prompt('同一角色，侧视'))
        self.assertIn('面朝左方',animation_prompt('向左'))
        english=animation_prompt('yellow cartoon dinosaur, standing still')
        self.assertIn('yellow cartoon dinosaur',english)
        self.assertNotIn('standing still',english)

    def test_chinese_color_and_body_part_binding_and_requested_clothing(self):
        graph=initial_character_workflow('黄色卡通小恐龙，白色肚皮，大眼睛，全身，侧视','','model',1)
        text=graph['2']['inputs']['text']
        self.assertIn('yellow skin',text)
        self.assertIn('white belly',text); self.assertNotIn('shoes visible',text)
        self.assertIn('jacket',graph['3']['inputs']['text'])
        dressed=initial_character_workflow('卡通小恐龙，穿黄色外套','','model',1)
        self.assertNotIn('jacket',dressed['3']['inputs']['text'])

    def test_chinese_negative_vocabulary_and_unknown_words_are_not_lost(self):
        compiled,unknown=negative_text('，'.join(NEGATIVE))
        self.assertEqual(unknown,''); self.assertIn('duplicate hands',compiled)
        self.assertIn('missing colors',compiled)
        compiled,unknown=negative_text('水印，未知约束，extra fingers')
        self.assertIn('未知约束',compiled); self.assertEqual(unknown,'未知约束')
        self.assertEqual(negative_text('blurry, watermark'),('blurry, watermark',''))

    def test_wan_graph_uses_temporal_experts_and_native_chinese_without_human_pose(self):
        positive=animation_prompt('黄色卡通角色，自然站立')
        self.assertNotIn('站立',positive)
        graph=video_workflow('reference.png',positive,'多余手臂，重影',42,20,33)
        self.assertEqual(graph['5']['inputs']['text'],positive)
        self.assertEqual(graph['6']['inputs']['text'],'多余手臂，重影')
        self.assertEqual(graph['8']['inputs']['start_image'],['7',0])
        self.assertEqual(graph['11']['inputs']['end_at_step'],graph['12']['inputs']['start_at_step'])
        self.assertEqual(graph['12']['inputs']['latent_image'],['11',0])
        self.assertEqual(graph['13']['class_type'],'VAEDecode')
        self.assertEqual(graph['15']['inputs']['samples'],['12',0])
        kinds={node['class_type'] for node in graph.values()}
        self.assertNotIn('DWPreprocessor',kinds); self.assertNotIn('ControlNetLoader',kinds)
        self.assertNotIn('IPAdapterAdvanced',kinds)
        with self.assertRaisesRegex(ValueError,'缺少模型'):
            info={kind:{'input':{'required':{}}} for kind in kinds}
            info['UNETLoader']['input']['required']['unet_name']=[[]]
            check_video_models(info)

    def test_nonhuman_reference_preserves_foreground_without_detector(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); path=root/'mascot.png'
            image=Image.new('RGBA',(180,240)); draw=ImageDraw.Draw(image)
            draw.ellipse((30,10,150,220),fill=(250,190,40,255)); image.save(path)
            with patch('aipictures.background.session',side_effect=AssertionError('already transparent')):
                result=prepare_subject(path,root/'input.png',threading.Event())
            self.assertEqual(result['method'],'foreground_only_no_human_pose')
            with Image.open(root/'reference_rgba.png') as foreground:
                self.assertEqual(foreground.getpixel((384,700)),(250,190,40,255))
                self.assertEqual(foreground.getpixel((0,0))[3],0)
            with Image.open(root/'input.png') as conditioning:
                self.assertEqual(conditioning.size,(576,768))

    def test_loop_selection_uses_distinct_ordered_source_frames(self):
        frames=[]
        for i in range(33):
            image=Image.new('RGBA',(48,64)); ImageDraw.Draw(image).rectangle((i%16,10,20+i%16,55),fill='orange')
            frames.append(image)
        for count in (8,16):
            indices,metadata=loop_indices(frames,count)
            self.assertEqual(len(indices),count); self.assertEqual(indices,sorted(set(indices)))
            self.assertLessEqual(indices[-1],32); self.assertGreater(metadata['end_exclusive'],metadata['start'])

    def test_whole_frame_stabilization_keeps_scale_colors_and_ground(self):
        images=[]
        for x,y in [(30,10),(42,17),(23,5)]:
            image=Image.new('RGBA',(180,240)); ImageDraw.Draw(image).rectangle((x,y,x+65,y+190),fill=(200,90,40,255))
            images.append(image)
        stable,metadata=stabilize_frames(images)
        boxes=[image.getchannel('A').point(lambda alpha:255 if alpha>128 else 0).getbbox() for image in stable]
        self.assertEqual(boxes[0],boxes[1]); self.assertEqual(boxes[0],boxes[2])
        self.assertLessEqual(abs(boxes[0][3]-978),1)
        self.assertEqual(stable[0].getpixel((384,600)),(200,90,40,255))
        self.assertEqual(metadata['method'],'whole_frame_only')

    def test_cancelled_preparation_never_submits_gpu_work(self):
        with tempfile.TemporaryDirectory() as temp:
            cancel=threading.Event(); cancel.set()
            with self.assertRaises(Cancelled):
                generate_temporal(None,temp,'','',1,8,8,lambda *args:None,cancel,reference='unused.png')
            record=json.loads((Path(temp)/'sequence.json').read_text('utf-8'))
            self.assertEqual(record['status'],'cancelled'); self.assertEqual(record['frames'],[])

    def test_cancelled_matte_rebuild_keeps_existing_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); existing=root/'frame_000.png'
            existing.write_bytes(b'existing export')
            cancel=threading.Event(); cancel.set()
            with self.assertRaises(Cancelled):
                finish_sequence(root,{}, {'frame_count':8,'fps':8},lambda *args:None,cancel)
            self.assertEqual(existing.read_bytes(),b'existing export')

    def test_inference_cache_release_respects_other_jobs(self):
        client=Mock(); client.request.return_value={'queue_running':[['another job']],'queue_pending':[]}
        self.assertFalse(release_idle_models(client)['released'])
        client.request.assert_called_once_with('/queue')
        client=Mock(); client.request.side_effect=[{'queue_running':[],'queue_pending':[]},{}]
        self.assertTrue(release_idle_models(client)['released'])
        client.request.assert_called_with('/free',{'unload_models':True,'free_memory':True})


if __name__=='__main__': unittest.main()
