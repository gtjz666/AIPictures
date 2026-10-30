"""Qt action selection, per-action endpoint playback, and explicit task-stage display."""
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw
from PySide6.QtTest import QTest

from aipictures.animation_actions import ACTIONS
from aipictures.app import Window, create_application
from aipictures.character_profile import rig_document
from aipictures.motion_clip import make_clip
from aipictures.motion_editor import MotionDialog
from aipictures.storage import DATA, write_json
from aipictures.walk_cycle import export_sequence


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        root=Path(temp)
        with patch('aipictures.app.DATA',root),patch('aipictures.walk_cycle.DATA',root), \
             patch.object(Window,'connect_engine'),patch.object(Window,'load_gallery'), \
             patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
             patch('aipictures.pose_animation.check_models'):
            window=Window();window.timer.stop();window.show();QTest.qWait(60)
            window.connected=True;window.client=Mock()
            window.info={'samplers':['euler'],'object_info':{},'nodes':['DWPreprocessor']}
            window.model.addItem('test');window.sampler.addItem('euler');window.scheduler.addItem('simple')
            window.start_next=Mock()
            source=root/'reference.png';image=Image.new('RGBA',(768,1024))
            ImageDraw.Draw(image).rectangle((320,50,440,978),fill=(100,60,150,255));image.save(source)
            window.set_reference(source);window.generation_type.setCurrentIndex(1);window.animation_source.setCurrentIndex(0)
            for action in ACTIONS:
                window.animation_action.setCurrentIndex(window.animation_action.findData(action))
                window.enqueue_walk();_,params,folder,item=window.pending[-1]
                assert params['action']==action and params['animation_detail']=='native'
                captured=[]
                def launch(worker,callback):
                    captured.append(callback);worker(lambda *_:None)
                window.launch=launch
                with patch('aipictures.pose_animation.generate') as generate:
                    window.start_walk(params,folder,item)
                    assert generate.call_args.args[12]==action
                    callback=captured[-1]
                    window.last_chat_graph={'8':{'class_type':'WanAnimateToVideo'}}
                    callback('pose_video_event',{'event':'executing','data':{'node':'8'}})
                    assert '采样前' in window.status.toolTip()
                    callback('pose_video_event',{'event':'cancel_pending','data':{'message':'正在等待后端确认取消…'}})
                    assert window.current is not None and '取消' in window.status.toolTip()
                window.current=None
                clip=make_clip(rig_document(),'a'*64,action)
                dialog=MotionDialog({'rgba':str(source)},clip)
                assert dialog.loop.isChecked()==(action!='jump')
                dialog.choice.setCurrentIndex(8)
                assert '第 8 / 8 帧' in dialog.frame_label.text()
                if action=='jump':assert '恢复站立' in dialog.frame_label.text()
                dialog.close()
                output=root/action;output.mkdir();frames=[]
                for i in range(8):
                    frame=output/f'frame_{i:03d}.png';sprite=image.copy()
                    ImageDraw.Draw(sprite).rectangle((350,100+i*10,390,110+i*10),fill=(i*20,100,100,255))
                    sprite.save(frame);frames.append(frame)
                exports=export_sequence(output,frames,8,action)
                write_json(output/'sequence.json',{'status':'completed','title':action,'action':action,'loop':action!='jump',
                    'fps':8,'frames':[{'image':p.name,'index':i,'stage':action} for i,p in enumerate(frames)],'exports':exports})
                player=window.animation_player;player.load(output/'sequence.json')
                for _ in range(8):player.advance()
                assert player.index==(7 if action=='jump' else 0)
                assert player.timer.isActive()==(action!='jump')
                if action=='jump':
                    player.toggle();assert player.index==0 and player.timer.isActive()
                    with Image.open(output/'jump.gif') as gif:assert 'loop' not in gif.info
                player.stop()
            window.pending.clear();window.current=None;window.close()
    print('All five Qt action bindings, stages, jump endpoint/replay and GIF loop flags passed.',flush=True)


if __name__=='__main__':main()
