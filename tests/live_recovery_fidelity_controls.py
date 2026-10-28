"""Real Qt controls with isolated cache; inject failure without stopping the user's server."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image,ImageDraw
from PySide6.QtCore import Qt,QPoint,QEvent
from PySide6.QtGui import QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QListWidgetItem,QToolTip

from aipictures.app import Window,create_application
from aipictures.engine import ComfyClient,EngineUnavailable
from aipictures.lora_catalog import entry_for
from aipictures.storage import DATA,write_json


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory(dir=DATA) as directory:
        root=Path(directory)
        with patch('aipictures.app.DATA',root),patch.object(Window,'connect_engine'),patch.object(Window,'load_gallery'),patch.object(Window,'restore_chat'):
            window=Window(); window.timer.stop(); window.show(); QTest.qWait(300)
            window.model.addItem('sd_xl_base_1.0_0.9vae.safetensors')
            window.sampler.addItem('dpmpp_2m'); window.scheduler.addItem('karras')
            window.lora.addItem('日系动漫','AIPictures/anime-slider-sdxl.safetensors'); window.lora.setCurrentIndex(1)
            selected=window.lora.currentData(); window.quality_mode.setCurrentIndex(1)
            source=root/'reference.png'; image=Image.new('RGBA',(256,384))
            ImageDraw.Draw(image).ellipse((60,15,196,368),fill=(190,50,95,255)); image.save(source)
            window.set_reference(source)
            assert window.preserving_reference()
            assert window.lora.currentData()==selected and not window.lora.isEnabled()
            assert not window.quality_mode.isEnabled() and window.denoise.maximum()==.25
            window.positive.setPlainText('蓝发，白色衬衫，自然站立')
            graph,params=window.graph_snapshot('reference.png')
            assert params['lora']=='' and params['quality_mode']=='off'
            assert graph['5']['inputs']['denoise']<=.25
            assert not any(n['class_type'] in ('LoraLoader','ImageUpscaleWithModel') for n in graph.values())
            assert 'navy-blue hair' not in graph['2']['inputs']['text']
            window.reference_policy.setCurrentIndex(1)
            assert window.lora.isEnabled() and window.quality_mode.isEnabled() and window.denoise.maximum()==1
            assert window.lora.currentData()==selected
            graph,params=window.graph_snapshot('reference.png')
            assert any(n['class_type']=='LoraLoader' for n in graph.values())
            assert any(n['class_type']=='ImageUpscaleWithModel' for n in graph.values())
            window.reference_policy.setCurrentIndex(0)
            window.open_settings('image'); QTest.qWait(100)
            window.settings_dialogs['image'].grab().save(str(DATA/'reference-policy-preview.png'))
            window.settings_dialogs['image'].close(); window.open_settings('sampling'); QTest.qWait(100)
            for name in ('model','reference_policy','quality_mode','steps','cfg','seed','sampler','scheduler',
                         'lora_category','lora','strength','animation_source','animation_engine','walk_count'):
                assert getattr(window,name).toolTip(),name
            # Deliver the same Qt help event used after the system's hover delay.
            point=QPoint(25,15)
            app.sendEvent(window.cfg,QHelpEvent(QEvent.Type.ToolTip,point,window.cfg.mapToGlobal(point)))
            QTest.qWait(150)
            assert QToolTip.isVisible()
            window.settings_dialogs['sampling'].grab().save(str(DATA/'hover-help-preview.png'))
            for widget in app.topLevelWidgets():
                if widget.isVisible() and widget.inherits('QTipLabel'):
                    widget.grab().save(str(DATA/'hover-tooltip-preview.png'))
            QToolTip.hideText(); window.settings_dialogs['sampling'].close()
            window.client=ComfyClient(); window.connected=True
            item=QListWidgetItem('pending'); window.queue_list.addItem(item)
            window.pending.append(({}, {},root/'queued',item))
            window.disconnect_engine(str(EngineUnavailable(window.client.url)))
            assert not window.connected and not window.generate_button.isEnabled()
            with patch.object(window,'start_walk') as start:
                window.start_next(); start.assert_not_called()
            assert len(window.pending)==1 and '重新连接' in item.text()
            # Reconnection consumes only jobs that had not yet started.
            window.pending.clear(); window.current=None
            callbacks=[]
            window.launch=lambda action,callback:callbacks.append(callback)
            window.start_engine(); assert window.engine_starting and not window.start_engine_button.isEnabled()
            callbacks[-1]('result',True)
            assert not window.engine_starting and window.start_engine_button.isEnabled()
            window.connect_engine.assert_called()
            window.clear_reference(); assert window.preview_path is None
            assert window.lora.isEnabled() and window.quality_mode.isEnabled()
            window.close()
    write_json(DATA/'recovery-fidelity-controls-acceptance.json',{
        'passed':True,'real_qt_hover_visible':True,'reference_preserve_default':True,
        'style_and_restoration_retained_but_not_applied':True,'explicit_redraw_restores_manual_choices':True,
        'source_appearance_overrides_text':True,'disconnect_pauses_unstarted_jobs':True,
        'one_click_start_connects_when_ready':True,'no_user_server_stopped':True})
    print('Recovery, hover help and reference fidelity Qt checks passed.',flush=True)


if __name__=='__main__': main()
