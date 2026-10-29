import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from aipictures.general_image import positive_text,reference_workflow,finish_output
from aipictures.prompt_binding import bind_request,check_models
from aipictures.workflow import ImageRequest


class GeneralImageTests(unittest.TestCase):
    def test_windows_model_separator_uses_the_backend_canonical_name(self):
        graph={'1':{'class_type':'LoraLoader','inputs':{'lora_name':'AIPictures/crayon-sdxl.safetensors'}}}
        info={'LoraLoader':{'input':{'required':{'lora_name':[['AIPictures\\crayon-sdxl.safetensors']]}}}}
        check_models(graph,info)
        self.assertEqual(graph['1']['inputs']['lora_name'],'AIPictures\\crayon-sdxl.safetensors')
        graph['1']['inputs']['lora_name']='missing.safetensors'
        with self.assertRaisesRegex(ValueError,'缺少模型'): check_models(graph,info)

    def test_independent_view_subject_and_scene_requests(self):
        for text,expected in [('正面全身，面向镜头','front view'),('背面视图','back view'),
                ('俯视图，红色药水，药水瓶','top-down view'),('等距视角，木箱','isometric view'),
                ('背景场景，森林，黄昏，无人','environment background'),('双人，坐姿','two people')]:
            prompt,_=positive_text(text)
            self.assertIn(expected,prompt)
            self.assertNotIn('side profile',prompt)
            self.assertNotIn('standing',prompt)
        self.assertIn('自定义珐琅穹顶',positive_text('自定义珐琅穹顶')[0])

    def test_reference_is_conditioning_not_a_locked_pose(self):
        request=ImageRequest('sd_xl_base.safetensors','front view of a wizard',negative='')
        graph,mapping=bind_request(reference_workflow(request,'ref.png',.45),request,'ref.png')
        self.assertEqual(graph['5']['inputs']['latent_image'],['4',0])
        self.assertEqual(graph['5']['inputs']['denoise'],1)
        self.assertEqual(graph['reference_condition']['inputs']['weight'],.45)
        self.assertEqual(mapping['reference'],['reference'])
        self.assertFalse(any(n['class_type'].startswith('ControlNet') for n in graph.values()))
        self.assertFalse(any(n['class_type']=='LoadImage' for n in reference_workflow(request,'ref.png',0).values()))

    def test_requested_small_edit_still_uses_source_latent(self):
        request=ImageRequest('sd_xl_base.safetensors','preserve outfit, open eyes',negative='')
        graph,_=bind_request(reference_workflow(request,'ref.png'),request,'ref.png',.6,True)
        self.assertEqual(graph['5']['inputs']['denoise'],.25)
        self.assertTrue(any(n['class_type']=='VAEEncode' for n in graph.values()))

    def test_full_environment_output_keeps_original_pixels_and_skips_matting(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);path=folder/'landscape.png';Image.new('RGB',(32,24),'forestgreen').save(path)
            before=hashlib.sha256(path.read_bytes()).hexdigest();result={'images':[str(path)]}
            with patch('aipictures.background.process_result',side_effect=AssertionError('must not remove scene')):
                self.assertIs(finish_output(result,folder,lambda *a:None,threading.Event()),result)
            self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
