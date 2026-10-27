"""Real Qt dialogs, prompt bindings, explicit save and deletion of isolated test caches."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import QPoint,QTimer,Qt
from PySide6.QtGui import QPalette

from aipictures.app import Window,create_application
from aipictures.result_cache import ResultCache
from aipictures.storage import DATA,write_json

base=DATA/'test-cache'; base.mkdir(exist_ok=True)
temporary=tempfile.TemporaryDirectory(prefix='settings-',dir=base)
test_root=Path(temporary.name).resolve(); assert test_root.is_relative_to(base.resolve())
store=ResultCache(test_root)
for name in ('remove','busy'):
    folder=test_root/'jobs'/name; write_json(folder/'job.json',{'status':'completed'})
    Image.new('RGBA',(64,64),(200,80,30,255)).save(folder/'image_000.png')
app=create_application([]); window=Window(); window.show()
state={'stage':'connect','start':time.monotonic(),'code':0}


def tick():
    if time.monotonic()-state['start']>90: raise TimeoutError(state['stage'])
    if state['stage']=='connect' and window.connected:
        window.timer.stop(); window.cache_store=store; window.load_gallery()
        assert window.positive.isVisible() and window.negative.isVisible()
        assert window.palette().color(QPalette.ColorRole.Window).lightness()>240
        positive=window.positive.mapTo(window,QPoint(0,0)); negative=window.negative.mapTo(window,QPoint(0,0))
        assert abs(positive.y()-negative.y())<2 and negative.x()>positive.x()
        assert not any(dialog.isVisible() for dialog in window.settings_dialogs.values())
        for key in ('image','sampling','connection'):
            window.open_settings(key); assert window.settings_dialogs[key].isVisible()
            assert sum(dialog.isVisible() for dialog in window.settings_dialogs.values())==1
        window.settings_dialogs['connection'].close()
        window.open_settings('creation'); window.generation_type.setCurrentIndex(1)
        assert window.settings_dialogs['creation'].isVisible() and window.walk_settings.isVisible()
        window.walk_fps.setValue(10)
        window.open_settings('sampling')
        assert window.settings_dialogs['sampling'].isVisible() and not window.settings_dialogs['creation'].isVisible()
        window.steps.setValue(21); window.open_settings('creation')
        assert window.walk_fps.value()==10 and window.steps.value()==21
        app.processEvents()
        window.grab().save(str(DATA/'floating-settings-studio.png'))
        window.settings_dialogs['creation'].grab().save(str(DATA/'floating-generation-settings.png'))
        window.settings_dialogs['creation'].close()
        window.generation_type.setCurrentIndex(0); window.apply_character(route='baseline')
        window.negative.setPlainText('watermark, extra fingers, blurry')
        window.positive.setPlainText('全身，侧视')
        graph,params=window.graph_snapshot('__reference__')
        assert graph['3']['inputs']['text']=='watermark, extra fingers, blurry'
        from aipictures.walk_cycle import frame_workflow
        walk=frame_workflow('ref','pose','guide',1,'walk',window.model.currentText(),negative=window.negative.toPlainText())
        assert walk['3']['inputs']['text']==graph['3']['inputs']['text']
        # Queue a real application request without dispatching a GPU job, inspect the snapshot.
        queued=test_root/'animations'/'queued'
        window.generation_type.setCurrentIndex(1)
        window.positive.setPlainText('人物原地向右走路')
        with patch('aipictures.walk_cycle.new_sequence',return_value=queued),patch.object(window,'start_next'):
            window.enqueue_walk()
        assert window.pending[-1][1]['negative']=='watermark, extra fingers, blurry'
        window.clear_pending(); window.generation_type.setCurrentIndex(0)
        # Exercise the actual Save action with a chosen test destination.
        source=test_root/'jobs'/'remove'/'image_000.png'; saved=test_root/'chosen.png'
        window.show_image(str(source))
        with patch('aipictures.app.QFileDialog.getSaveFileName',return_value=(str(saved),'PNG (*.png)')):
            window.save_as()
        assert saved.read_bytes()==source.read_bytes() and len(store.saved_files())==1
        window.open_assets(); window.assets_dialog.grab().save(str(DATA/'cache-history-panel.png'))
        assert window.assets_dialog.saved_files.count()==1
        window.pending.append((None,{},test_root/'jobs'/'busy',None))
        # Only disposable fixtures in store are eligible; user's real result folders are untouched.
        for i in range(window.gallery.count()):
            item=window.gallery.item(i)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole+1)==str(source.parent))
        window.clear_result_cache('image',False); state['stage']='clearing_selected'
    elif state['stage']=='clearing_selected' and not window.cache_busy:
        assert not (test_root/'jobs'/'remove').exists()
        assert (test_root/'chosen.png').is_file()
        assert window.output is None and window.animation_player.manifest is None
        window.clear_result_cache('image',True); state['stage']='clearing'
    elif state['stage']=='clearing' and not window.cache_busy:
        assert not (test_root/'jobs'/'remove').exists()
        assert (test_root/'jobs'/'busy'/'image_000.png').is_file()
        assert (test_root/'chosen.png').is_file() and len(store.saved_files())==1
        assert '跳过 1' in window.assets_dialog.cache_status.text()
        assert window.output is None and window.animation_player.manifest is None
        window.pending.clear(); window.assets_dialog.close()
        write_json(DATA/'settings-cache-acceptance.json',{'passed':True,'paired_prompts':True,
            'light_theme':True,
            'floating_settings_reused':True,'negative_image_and_walk_binding':True,
            'explicit_export_preserved':True,'active_cache_skipped':True,'selected_cache_removed':True})
        print('Floating settings, paired prompts, saved exports and protected cache cleanup passed.',flush=True)
        state['stage']='exit'
    elif state['stage']=='exit' and not window.workers:
        window.pending.clear(); app.exit(state['code'])


def guard():
    try: tick()
    except Exception as exc:
        print('FAIL',repr(exc),flush=True); window.pending.clear(); window.timer.stop(); state['stage']='exit'; state['code']=1


timer=QTimer(); timer.timeout.connect(guard); timer.start(150)
code=app.exec()
assert test_root.is_relative_to(base.resolve()); temporary.cleanup()
sys.exit(code)
