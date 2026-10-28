"""Real Qt controls: manual style selection, empty startup reference, selected-image preview."""
import hashlib
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.character_profile import character_workflow
from aipictures.lora_catalog import catalog,entry_for
from aipictures.storage import DATA,write_json
from aipictures.prompt_defaults import default_prompts


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        root=Path(temp); (root/'chat').mkdir()
        write_json(root/'chat/active-workflow.json',{'character_id':'old-default','graph':character_workflow('old-reference.png'),'title':'old'})
        with patch('aipictures.app.DATA',root),patch.object(Window,'load_gallery',lambda self:None),patch.object(Window,'restore_chat',lambda self:None):
            window=Window(); window.show(); started=time.monotonic()
            while not window.connected and time.monotonic()-started<20: QTest.qWait(100)
            assert window.connected
            assert window.reference_path is None and window.character_profile is None
            assert window.pixmap.isNull() and window.preview.pixmap().isNull()
            assert window.lora.currentData()=='' and window.quality_mode.currentData()=='off'
            assert not (root/'references').exists()
            assert (window.positive.toPlainText(),window.negative.toPlainText())==default_prompts()
            window.grab().save(str(DATA/'prompt-defaults-preview.png'))
            window.generation_type.setCurrentIndex(1)
            assert (window.positive.toPlainText(),window.negative.toPlainText())==default_prompts(True,False)
            edited=('我自己的角色描述','我自己的反向限制')
            window.positive.setPlainText(edited[0]); window.negative.setPlainText(edited[1])
            window.generation_type.setCurrentIndex(0)
            assert (window.positive.toPlainText(),window.negative.toPlainText())==edited
            QTest.mouseClick(window.reset_prompts_button,Qt.MouseButton.LeftButton)
            assert (window.positive.toPlainText(),window.negative.toPlainText())==default_prompts()
            assert window.lora.currentData()==''
            window.positive.setPlainText('动漫，写实摄影，像素画，漫画')
            assert window.lora.currentData()==''
            window.lora_category.setCurrentText('动漫')
            assert window.lora.currentData()==''
            assert window.lora.count()==4
            chosen=next(window.lora.itemData(i) for i in range(1,window.lora.count()) if entry_for(window.lora.itemData(i))['id']=='anime-slider')
            window.lora.setCurrentIndex(window.lora.findData(chosen))
            assert window.strength.value()==2
            window.positive.setPlainText('realistic photo of a person')
            assert window.lora.currentData()==chosen
            window.open_settings('sampling'); QTest.qWait(150)
            window.settings_dialogs['sampling'].grab().save(str(DATA/'style-selection-preview.png'))
            window.settings_dialogs['sampling'].close()
            source=root/'test-reference.png'; image=Image.new('RGBA',(128,192))
            ImageDraw.Draw(image).ellipse((24,12,104,180),fill=(90,50,150,255)); image.save(source)
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            window.set_reference(source)
            assert window.preview_role=='reference' and window.output is None
            assert not window.pixmap.isNull() and window.pixmap.width()==128
            assert window.preview_path==str(window.reference_path)
            assert hashlib.sha256(window.reference_path.read_bytes()).hexdigest()==before
            assert window.positive.toPlainText()=='realistic photo of a person'
            window.open_current_image(); QTest.qWait(100)
            viewer=window.image_viewer
            viewer.view.original_size(); viewer.view.zoom(1.25)
            assert viewer.view.item.transformationMode()==Qt.TransformationMode.SmoothTransformation
            viewer.smoothing.setChecked(False)
            assert viewer.view.item.transformationMode()==Qt.TransformationMode.FastTransformation
            viewer.close()
            QTest.mouseClick(window.reset_prompts_button,Qt.MouseButton.LeftButton)
            assert (window.positive.toPlainText(),window.negative.toPlainText())==default_prompts(False,True)
            assert window.lora.currentData()==chosen
            window.activate_template(character_workflow('placeholder.png'),'restored workflow',preserve_prompts=True)
            assert window.negative.toPlainText()==default_prompts(False,True)[1]
            window.activate_template(character_workflow('placeholder.png'),'reference workflow')
            window.reference_policy.setCurrentIndex(window.reference_policy.findData('redraw'))
            graph,params=window.graph_snapshot('__chosen_reference__')
            key='aipictures_style_lora'
            assert graph[key]['inputs']['lora_name']==chosen
            assert graph['13']['inputs']['model']==[key,0] and graph['2']['inputs']['clip']==[key,1]
            assert 'anime' in graph['2']['inputs']['text'] and params['lora_style']['id']=='anime-slider'
            window.clear_reference()
            assert window.reference_path is None and window.preview_path is None
            assert window.preview.pixmap().isNull() and window.pixmap.isNull()
            window.positive.setPlainText('a realistic portrait, anime, pixel art')
            window.lora.setCurrentIndex(0)
            graph,params=window.graph_snapshot()
            assert not any(n['class_type'] in ('LoraLoader','LoadImage') for n in graph.values())
            window.generation_type.setCurrentIndex(1)
            assert window.animation_source.currentData()=='text' and window.lora.isEnabled()
            window.animation_source.setCurrentIndex(0); assert not window.lora.isEnabled()
            assert hashlib.sha256(source.read_bytes()).hexdigest()==before
            window.timer.stop(); window.close()
    write_json(DATA/'style-controls-acceptance.json',{'passed':True,'manual_category_and_lora_selection':True,
        'prompt_does_not_select_lora':True,'startup_has_no_reference':True,'old_character_not_restored':True,
        'selected_reference_displayed_unchanged':True,'clear_reference_clears_preview':True,
        'lora_reaches_template_model_and_clip':True,'smooth_zoom_and_pixel_toggle':True,
        'chinese_prompts_prefilled':True,'pristine_defaults_follow_generation_type':True,
        'edited_prompts_preserved':True,'one_click_restore_defaults':True})
    print('Manual style, empty/selected reference and smooth zoom checks passed.',flush=True)


if __name__=='__main__': main()
