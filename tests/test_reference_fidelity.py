import unittest

from aipictures.action_intent import parse_intent
from aipictures.prompt_binding import bind_request, image_sources
from aipictures.reference_fidelity import reference_positive
from aipictures.temporal_animation import animation_prompt
from aipictures.workflow import ImageRequest, build_workflow


class ReferenceFidelityTests(unittest.TestCase):
    def setUp(self):
        self.request=ImageRequest('model','same character',seed=9)

    def test_identity_adapter_cannot_leave_preserve_generation_at_full_noise(self):
        template=build_workflow(self.request)
        template['10']={'class_type':'LoadImage','inputs':{'image':'old.png'}}
        template['11']={'class_type':'IPAdapterAdvanced','inputs':{'image':['10',0]}}
        graph,mapping=bind_request(template,self.request,'new.png',.8,preserve_reference=True)
        self.assertEqual(graph['5']['inputs']['denoise'],.25)
        sources=image_sources(graph,graph['5']['inputs']['latent_image'])
        self.assertTrue(sources)
        self.assertTrue(set(sources).issubset(mapping['reference']))
        self.assertTrue(all(graph[node]['inputs']['image']=='new.png' for node in mapping['reference']))
        self.assertEqual(template['5']['inputs']['denoise'],1.)
        self.assertEqual(template['10']['inputs']['image'],'old.png')

    def test_existing_tiled_decoder_accepts_reference_latents(self):
        graph=build_workflow(self.request); graph['6']['class_type']='VAEDecodeTiled'
        result,_=bind_request(graph,self.request,'ref.png',.12,preserve_reference=True)
        self.assertEqual(result['5']['inputs']['denoise'],.12)
        self.assertTrue(image_sources(result,result['5']['inputs']['latent_image']))

    def test_authored_style_nodes_are_not_silently_ignored_in_preserve_mode(self):
        graph=build_workflow(self.request)
        graph['20']={'class_type':'LoraLoader','inputs':{'model':['1',0]}}
        with self.assertRaisesRegex(ValueError,'预设自带'):
            bind_request(graph,self.request,'ref.png',.2,preserve_reference=True)

    def test_adapter_and_distinct_latent_image_both_receive_user_reference(self):
        graph,_=bind_request(build_workflow(self.request),self.request,'latent.png',.6)
        graph['20']={'class_type':'LoadImage','inputs':{'image':'identity.png'}}
        graph['21']={'class_type':'IPAdapterAdvanced','inputs':{'image':['20',0]}}
        bound,mapping=bind_request(graph,self.request,'user.png',.2,preserve_reference=True)
        self.assertEqual(len(mapping['reference']),2)
        self.assertTrue(all(bound[key]['inputs']['image']=='user.png' for key in mapping['reference']))

    def test_pose_constraints_require_explicit_redraw(self):
        graph=build_workflow(self.request)
        graph['10']={'class_type':'ControlNetApplyAdvanced','inputs':{'positive':['2',0],'negative':['3',0]}}
        graph['5']['inputs'].update(positive=['10',0],negative=['10',1])
        with self.assertRaisesRegex(ValueError,'允许按描述重绘'):
            bind_request(graph,self.request,'ref.png',.2,preserve_reference=True)
        bound,_=bind_request(graph,self.request,'ref.png',.6)
        self.assertEqual(bound['5']['inputs']['denoise'],.6)

    def test_static_reference_appearance_is_not_overridden_by_prose(self):
        positive=reference_positive(parse_intent('蓝发，白色衬衫，向前伸手'))
        self.assertIn('reaching forward',positive)
        self.assertNotIn('navy-blue',positive); self.assertNotIn('white blouse',positive)
        self.assertIn('garment patterns',positive)

    def test_temporal_preserve_ignores_recoloring_and_rotation_but_keeps_pace(self):
        positive=animation_prompt('黄色卡通小恐龙，向左，缓慢，自然站立',True)
        self.assertIn('保持参考图朝向',positive); self.assertIn('缓慢行走',positive)
        self.assertNotIn('面朝左',positive); self.assertNotIn('外观和细节补充',positive)
        self.assertNotIn('黄色',positive); self.assertNotIn('站立',positive)
        self.assertIn('纹样',positive)


if __name__=='__main__': unittest.main()
