import threading
import unittest
from copy import deepcopy
import numpy as np
from PIL import Image,ImageDraw
from aipictures.workflow import ImageRequest,build_workflow
from aipictures.prompt_binding import bind_request
from aipictures.lora_catalog import catalog,entry_for,style_prompt,bind_lora
from aipictures.character_profile import character_workflow
from aipictures.image_quality import smooth_alpha,append_quality,check_quality_models,MODELS
from aipictures.temporal_animation import initial_character_workflow,video_workflow


class StyleQualityTests(unittest.TestCase):
    def test_catalog_files_are_unique_and_use_verified_sdxl_sources(self):
        entries=catalog()
        self.assertEqual(len(entries),12); self.assertEqual(len({v['filename'] for v in entries}),12)
        self.assertTrue({'动漫','写实','卡通','插画','像素'}<={v['category'] for v in entries})
        for entry in entries:
            self.assertEqual(len(entry['download']['sha256']),64)
            self.assertIn(entry['download']['revision'],entry['download']['url'])
            self.assertEqual(entry_for(entry['filename'].replace('/','\\'))['id'],entry['id'])

    def test_no_selection_never_chooses_style_from_prompt(self):
        positive='anime, cartoon, realistic photo, manga, pixel art'
        self.assertEqual(style_prompt(positive,''),(positive,None))
        graph=build_workflow(ImageRequest('sdxl',positive))
        graph,_=bind_request(graph,ImageRequest('sdxl',positive))
        self.assertNotIn('LoraLoader',{node['class_type'] for node in graph.values()})

    def test_manual_style_inserts_trigger_once_and_rejects_wrong_base(self):
        name=catalog()[0]['filename']
        positive,meta=style_prompt('a portrait',name)
        self.assertIn('anime',positive); self.assertEqual(meta['category'],'动漫')
        self.assertEqual(style_prompt(positive,name)[0],positive)
        graph=build_workflow(ImageRequest('sdxl','portrait'))
        with self.assertRaises(ValueError): bind_lora(graph,name,1,'flux1-dev.safetensors')

    def test_template_lora_reaches_ipadapter_and_clip_without_touching_vae(self):
        template=character_workflow('ref.png'); original=deepcopy(template)
        request=ImageRequest('sd_xl_base_1.0.safetensors','same character',lora=catalog()[0]['filename'])
        graph,_=bind_request(template,request,'new.png')
        key='aipictures_style_lora'
        self.assertEqual(graph['13']['inputs']['model'],[key,0])
        self.assertEqual(graph['2']['inputs']['clip'],[key,1])
        self.assertEqual(graph['6']['inputs']['vae'],['1',2])
        self.assertEqual(template,original)
        graph,_=bind_request(graph,request,'new.png')
        self.assertEqual(sum(n['class_type']=='LoraLoader' for n in graph.values()),1)
        request.lora=''; graph,_=bind_request(graph,request,'new.png')
        self.assertEqual(graph['13']['inputs']['model'],['1',0])

    def test_author_lora_is_preserved_and_our_layer_can_be_removed(self):
        graph=build_workflow(ImageRequest('sdxl','portrait',lora='author.safetensors'))
        graph['8'].pop('_meta'); original_vae=deepcopy(graph['6']['inputs']['vae'])
        bind_lora(graph,catalog()[0]['filename'],.7,'sdxl')
        self.assertEqual(graph['8']['inputs']['model'],['aipictures_style_lora',0])
        bind_lora(graph,'',0,'sdxl')
        self.assertEqual(graph['8']['inputs']['model'],['1',0])
        self.assertEqual(graph['8']['inputs']['lora_name'],'author.safetensors')
        self.assertEqual(graph['6']['inputs']['vae'],original_vae)

    def test_imported_numeric_node_links_receive_the_selected_lora(self):
        graph=build_workflow(ImageRequest('sdxl','portrait'))
        graph['5']['inputs']['model']=[1,0]; graph['2']['inputs']['clip']=[1,1]
        bind_lora(graph,catalog()[0]['filename'],.8,'sdxl')
        self.assertEqual(graph['5']['inputs']['model'],['aipictures_style_lora',0])
        self.assertEqual(graph['2']['inputs']['clip'],['aipictures_style_lora',1])

    def test_text_animation_lora_is_on_character_image_only(self):
        name=catalog()[0]['filename']
        graph=initial_character_workflow('人物，侧视，全身','','sdxl',1,20,name,2)
        self.assertEqual(graph['8']['inputs']['lora_name'],name)
        self.assertIn('anime',graph['2']['inputs']['text'])
        self.assertNotIn('LoraLoader',{n['class_type'] for n in video_workflow('ref','walk','',1).values()})

    def test_silhouette_smoothing_preserves_rgb_and_openings(self):
        im=Image.new('RGBA',(64,64),(80,30,100,0)); draw=ImageDraw.Draw(im)
        draw.polygon([(8,8),(56,56),(8,56)],fill=(80,30,100,255))
        draw.rectangle((16,38,24,46),fill=(80,30,100,0))
        result=smooth_alpha(im); before=np.asarray(im); after=np.asarray(result)
        self.assertTrue(np.array_equal(before[:,:,:3],after[:,:,:3]))
        self.assertEqual(result.getpixel((0,0))[3],0); self.assertEqual(result.getpixel((20,42))[3],0)
        self.assertEqual(result.getpixel((16,52))[3],255)
        self.assertGreater(int(((after[:,:,3]>0)&(after[:,:,3]<255)).sum()),30)

    def test_restoration_is_explicit_and_handles_new_comfy_combo_schema(self):
        graph=build_workflow(ImageRequest('sdxl','portrait')); original=deepcopy(graph)
        append_quality(graph,'off',512,640); self.assertEqual(graph,original)
        append_quality(graph,'anime',512,640)
        self.assertEqual(graph['7']['inputs']['images'],['aipictures_quality_resize_0',0])
        self.assertEqual(graph['aipictures_quality_model']['inputs']['model_name'],MODELS['anime'])
        info={name:{} for name in ('UpscaleModelLoader','ImageUpscaleWithModel','ImageScale')}
        info['UpscaleModelLoader']={'input':{'required':{'model_name':['COMBO',{'options':list(MODELS.values())}]}}}
        check_quality_models(info,'anime')


if __name__=='__main__': unittest.main()
