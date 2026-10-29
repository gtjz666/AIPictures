"""Real Qt controls -> queued parameters -> animation generator, without a GPU job."""
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image,ImageDraw
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.storage import DATA


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        root=Path(temp)
        with patch('aipictures.app.DATA',root),patch('aipictures.walk_cycle.DATA',root), \
             patch.object(Window,'connect_engine'),patch.object(Window,'load_gallery'), \
             patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
             patch('aipictures.pose_animation.check_models'):
            window=Window();window.timer.stop();window.show();QTest.qWait(100)
            window.connected=True
            window.client=Mock()
            window.info={'samplers':['euler','dpmpp_2m'],'object_info':{},'nodes':['DWPreprocessor']}
            window.model.addItem('test-model');window.sampler.addItem('euler');window.scheduler.addItem('simple')
            window.start_next=Mock()
            source=root/'source.png';image=Image.new('RGBA',(128,192))
            ImageDraw.Draw(image).rectangle((45,8,83,180),fill=(100,60,150,255));image.save(source)
            window.set_reference(source)
            window.generation_type.setCurrentIndex(1)
            window.animation_source.setCurrentIndex(0)
            assert window.animation_detail.currentData()=='native'
            assert window.animation_color.currentData()=='original'
            assert window.animation_detail.isEnabled() and window.animation_sampler.isEnabled()
            assert '768×1024' in window.animation_detail.toolTip()
            window.positive.setPlainText('自己的角色描述')
            for detail,sampler,color in (('native','euler','original'),('preview','dpmpp_2m','reference')):
                window.animation_detail.setCurrentIndex(window.animation_detail.findData(detail))
                window.animation_sampler.setCurrentIndex(window.animation_sampler.findData(sampler))
                window.animation_color.setCurrentIndex(window.animation_color.findData(color))
                window.enqueue_walk()
                _,params,folder,item=window.pending[-1]
                assert params['animation_detail']==detail and params['animation_sampler']==sampler
                assert params['animation_color']==color
                assert window.positive.toPlainText()=='自己的角色描述'
                with patch('aipictures.pose_animation.generate') as generate:
                    window.launch=lambda action,callback:action(lambda *_:None)
                    window.start_walk(params,folder,item)
                    assert generate.call_args.kwargs['detail']==detail
                    assert generate.call_args.kwargs['sampler']==sampler
                    assert generate.call_args.kwargs['color_mode']==color
                window.current=None
            window.animation_detail.setCurrentIndex(0)
            window.open_settings('creation');QTest.qWait(100)
            window.settings_dialogs['creation'].grab().save(str(DATA/'animation-detail-controls.png'))
            window.settings_dialogs['creation'].close()
            window.generation_type.setCurrentIndex(0)
            assert not window.animation_detail.isEnabled()
            assert not window.animation_sampler.isEnabled()
            assert not window.animation_color.isEnabled()
            window.pending.clear();window.current=None;window.close()
    print('Animation detail controls, saved parameters and generator bindings passed.',flush=True)


if __name__=='__main__':main()
