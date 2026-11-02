"""Actual light Qt layout, applicable controls and deterministic model-family routing."""
import tempfile
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from PIL import Image
from aipictures.app import Window,create_application
from aipictures import zimage


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)),\
         patch.object(Window,'connect_engine'),patch.object(Window,'load_gallery'),\
         patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        window=Window();window.timer.stop();window.show();QTest.qWait(30)
        assert window.generation_type.isVisible() and not window.animation_action.isVisible()
        assert not window.reference_path and not window.reference_policy.isVisible()
        assert not window.generate_button.toolTip() and not window.positive.toolTip()
        assert window.cfg.toolTip() and window.strength.toolTip()
        window.width.setValue(896);window.height.setValue(1152)
        window.positive.setPlainText('角色平躺在地上，白色衬衫')
        window.generation_type.setCurrentIndex(1)
        assert window.animation_action.isVisible() and not window.reference_policy.isVisible()
        assert '完整动画预览' in window.intent_hint.text()
        assert window.animation_engine.currentData()=='video_wan'
        assert not window.research_bones_button.isVisible()
        window.animation_action.setCurrentIndex(window.animation_action.findData('custom'))
        assert window.custom_strategy.currentData()=='free' and not window.custom_description.isVisible()
        assert window.positive.isVisible()
        assert not window.custom_loop.isVisible() and not window.motion_mode.isVisible()
        window.generation_type.setCurrentIndex(0)
        assert (window.width.value(),window.height.value())==(896,1152)
        window.model.addItem('sd_xl_base_1.0_0.9vae.safetensors')
        window.sampler.addItems(['dpmpp_2m','euler']);window.scheduler.addItems(['karras','simple'])
        window.model_family.model().item(1).setEnabled(True)
        window.info={'object_info':{
            'UNETLoader':{'input':{'required':{'unet_name':[[zimage.UNET]]}}},
            'CLIPLoader':{'input':{'required':{'clip_name':[[zimage.ENCODER]]}}},
            'VAELoader':{'input':{'required':{'vae_name':[[zimage.VAE]]}}},
            'EmptySD3LatentImage':{},'ModelSamplingAuraFlow':{},'ConditioningZeroOut':{}}}
        steps,cfg=window.steps.value(),window.cfg.value()
        window.model_family.setCurrentIndex(1)
        assert not window.lora.isEnabled() and not window.translate_prompt.isVisible()
        assert window.steps.value()==9 and window.cfg.value()==1.
        window.positive.setPlainText('一个红色药水瓶，俯视图');window.negative.setPlainText('文字，水印')
        window.seed.setText('1234')
        graph,params=window.graph_snapshot()
        assert params['model_family']=='zimage' and '一个红色药水瓶' in graph['text']['inputs']['text']
        assert graph['sample']['inputs']['seed']==1234 and graph['sample']['inputs']['cfg']==1.
        assert not any(node['class_type']=='LoraLoader' for node in graph.values())
        window.connected=True
        window.custom_graph={'imported':{}}
        window.generation_type_changed()
        assert window.workflow_selector.isEnabled() and '自动选择' in window.model_note.text()
        window.custom_graph=None
        window.model_family.setCurrentIndex(0)
        assert window.steps.value()==steps and window.cfg.value()==cfg
        window.model_family.setCurrentIndex(1)
        source=Path(temp)/'reference.png'
        Image.new('RGBA',(64,96),(80,120,180,255)).save(source)
        before=source.read_bytes()
        window.set_reference(str(source))
        assert window.model_family.currentData()=='sdxl'
        assert not window.model_family.model().item(1).isEnabled()
        assert window.reference_policy.isVisible() and window.reference_strength.isVisible()
        assert window.preview_role=='reference' and not window.pixmap.isNull()
        assert source.read_bytes()==before
        window.clear_reference()
        assert not window.reference_path and not window.reference_policy.isVisible()
        from aipictures.walk_cycle import export_sequence
        from aipictures.result_cache import ResultCache
        window.cache_store=ResultCache(Path(temp)/'cache')
        frames=[]
        for i in range(8):
            path=Path(temp)/f'frame_{i:03d}.png'
            Image.new('RGBA',(64,96),(60,90+i,150,255)).save(path);frames.append(path)
        exports=export_sequence(Path(temp),frames,8,'custom',loop=True)
        manifest=Path(temp)/'sequence.json'
        manifest.write_text(json.dumps({'status':'completed','method':'native_video_frames',
            'action':'custom','fps':8,'loop':True,'canvas':[64,96],'exports':exports,
            'frames':[{'image':p.name,'index':i,'stage':'关键姿态','source_time':i/8} for i,p in enumerate(frames)]}),encoding='utf-8')
        window.animation_player.load(manifest);window.animation_player.timer.stop()
        assert len(window.animation_player.frames)==8 and window.sequence_preview.frames.count()==8
        exported=Path(temp)/'animation.zip'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(exported),'ZIP')):
            window.animation_player.export()
        with zipfile.ZipFile(exported) as archive:
            assert json.loads(archive.read('animation.json'))['direction']=='source'
            assert archive.read(frames[0].name)==frames[0].read_bytes()
        window.close()
    print('Quality UI, visible modes, motion conflict, native Chinese and SDXL restore: PASS')


if __name__=='__main__':main()
