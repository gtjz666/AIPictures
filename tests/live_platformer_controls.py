"""Offscreen Qt integration: reference fidelity, explicit style opt-in and custom routes."""
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.storage import DATA,write_json
from aipictures.character_profile import rig_document
from aipictures.motion_language import make_custom_clip
from aipictures.motion_editor import MotionDialog
from aipictures.game_animation import export_game_data
from aipictures.walk_cycle import export_sequence


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        root=Path(temp)
        with patch('aipictures.app.DATA',root),patch('aipictures.walk_cycle.DATA',root),\
            patch.object(Window,'connect_engine'),patch.object(Window,'load_gallery'),\
            patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'),\
            patch('aipictures.pose_animation.check_models'),patch('aipictures.temporal_animation.check_video_models'):
            window=Window();window.timer.stop();window.show();QTest.qWait(40)
            window.connected=True;window.client=Mock()
            from aipictures.animation_style import style_workflow
            nodes={n['class_type'] for n in style_workflow('r','sdxl','manual.safetensors',.8,1).values()}|{'DWPreprocessor'}
            window.info={'samplers':['euler'],'object_info':{},'nodes':list(nodes),'loras':['AIPictures/anime-slider-sdxl.safetensors']}
            window.model.addItem('sd_xl_base_1.0_0.9vae.safetensors');window.refresh_loras();window.start_next=Mock()
            source=root/'reference.png';Image.new('RGBA',(768,1024),(90,60,130,255)).save(source)
            window.set_reference(source);window.generation_type.setCurrentIndex(1);window.animation_source.setCurrentIndex(0)
            assert window.animation_action.count()==7 and not window.animation_style.isChecked()
            window.lora.setCurrentIndex(1)
            assert not window.lora.isEnabled()
            window.animation_action.setCurrentIndex(window.animation_action.findData('attack'))
            window.enqueue_walk();params=window.pending[-1][1]
            assert params['lora']=='' and params['preserve_reference'] and not params['style_reference']
            window.animation_style.setChecked(True)
            assert window.lora.isEnabled() and window.model.isEnabled() and not window.motion_mode.isEnabled()
            assert '重绘风格基准' in window.reference_note.text()
            window.enqueue_walk();params=window.pending[-1][1]
            assert params['style_reference'] and params['lora'].endswith('anime-slider-sdxl.safetensors')
            window.animation_style.setChecked(False)
            window.animation_action.setCurrentIndex(window.animation_action.findData('custom'))
            window.custom_description.setPlainText('下蹲1秒，然后出拳1秒')
            assert '下蹲 → 基础攻击' in window.custom_hint.text()
            window.enqueue_walk();params=window.pending[-1][1]
            assert params['engine']=='animate' and params['custom_description']=='下蹲1秒，然后出拳1秒'
            window.custom_description.setPlainText('挥手告别')
            try:window.enqueue_walk()
            except ValueError:pass
            else:raise AssertionError('Unknown skeleton action must not silently become walking')
            window.custom_strategy.setCurrentIndex(1);window.enqueue_walk();params=window.pending[-1][1]
            assert params['engine']=='custom_free' and not window.motion_mode.isEnabled()
            captured=[]
            window.launch=lambda worker,callback:(captured.append(callback),worker(lambda *_:None))
            with patch('aipictures.custom_animation.generate') as generate:
                window.start_walk(params,window.pending[-1][2],window.pending[-1][3])
                assert generate.call_args.kwargs['custom_description']=='挥手告别'
                callback=captured[-1]
                window.last_chat_graph={str(i):{'class_type':'KSamplerAdvanced','inputs':{
                    'steps':20,'start_at_step':start,'end_at_step':end}} for i,start,end in ((11,0,10),(12,10,20))}
                callback('pose_video_event',{'event':'progress','data':{'node':'11','value':10,'max':10}})
                assert window.progress.value()==45
                callback('pose_video_event',{'event':'progress','data':{'node':'12','value':1,'max':10}})
                assert 45<window.progress.value()<55
                callback('pose_video_event',{'event':'progress','data':{'node':'12','value':10,'max':10}})
                assert window.progress.value()==80
            window.current=None
            clip=make_custom_clip(rig_document(),'a'*64,'下蹲，然后出拳')
            dialog=MotionDialog({'rgba':str(source)},clip)
            dialog.choice.setCurrentIndex(10)
            assert '第 10 / 16 帧' in dialog.frame_label.text()
            assert '基础攻击' in dialog.frame_label.text()
            dialog.reset_frame();dialog.reset_all()
            assert dialog.motion['motion_plan']==clip['motion_plan'];dialog.close()
            out=root/'preview';out.mkdir();frames=[]
            for i in range(8):
                p=out/f'frame_{i:03d}.png';Image.new('RGBA',(768,1024),(100+i,50,20,255)).save(p);frames.append(p)
            manifest={'status':'completed','action':'jump','title':'横版跳跃','loop':False,'fps':8,'canvas':[768,1024],
                'intent':{'direction':'right'},'frames':[{'image':p.name,'index':i,'stage':'跳跃','phase':i/7} for i,p in enumerate(frames)],
                'exports':export_sequence(out,frames,8,'jump')}
            export_game_data(out,manifest);write_json(out/'sequence.json',manifest)
            player=window.animation_player;player.load(out/'sequence.json');player.timer.stop()
            player.physics.setChecked(True);player.seek(3)
            assert window.pixmap.height()==1216 and window.output==str(frames[3])
            player.physics.setChecked(False);assert window.pixmap.height()==1024
            window.pending.clear();window.current=None;window.close()
    print('Qt platformer controls, optional LoRA, custom routing, editor and physics preview passed.')


if __name__=='__main__':main()
