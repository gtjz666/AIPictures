"""Real eight-frame GUI/ComfyUI acceptance; requires installed local character weights."""
import json
import os
import sys
import time
from uuid import uuid4
from PIL import Image
from PySide6.QtCore import QTimer
from aipictures.app import Window, create_application
from aipictures.storage import DATA, write_json
from aipictures.workflow_library import digest

os.environ['AIPICTURES_BROWSER_PROFILE']=str(DATA/'test-browser'/uuid4().hex)
app=create_application([]); window=Window(); window.show()
state={'stage':'connect','start':time.monotonic(),'progress':0,'frame_ready':0,'exit_code':0}
launch=window.launch


def wrapped(action,callback):
    def event(kind,data):
        if kind=='frame_event' and data['event']=='progress': state['progress']+=1
        if kind=='frame_ready':
            state['frame_ready']+=1; print('Frame',data['index']+1,'/',data['count'],flush=True)
        callback(kind,data)
    launch(action,event)
window.launch=wrapped


def tick():
    if time.monotonic()-state['start']>1800 and state['stage']!='exit': raise TimeoutError(state['stage'])
    if state['stage']=='connect' and window.connected:
        window.apply_character(route='baseline'); window.timer.stop()
        # Chinese input changes the actual prompt and chooses an independent pose input.
        window.positive.setPlainText('向前伸手，全身，侧视')
        graph,params=window.graph_snapshot('__reference__')
        assert params['pose']=='reach' and params['character_route']=='pose'
        assert 'reaching forward' in graph['2']['inputs']['text']
        assert graph['21']['inputs']['image'] in ('__aipictures_pose__','__adaptive_pose__')
        window.generation_type.setCurrentIndex(1)
        window.open_settings('creation')
        assert window.walk_settings.isVisible() and not window.character_route.isVisible()
        window.settings_dialogs['creation'].close()
        window.walk_count.setCurrentIndex(0); window.walk_fps.setValue(8); window.steps.setValue(24)
        window.positive.setPlainText('人物原地向右走路，侧视，全身，保持一致')
        window.seed.setText('20261027'); window.generate_button.click()
        assert window.current, window.chat_messages[-1]
        state['folder']=window.current['folder']; state['stage']='generation'
        window.grab().save(str(DATA/'walk-studio-before.png'))
        print('Animation folder:',state['folder'],flush=True)
    elif state['stage']=='generation' and not window.current:
        folder=state['folder']; job=json.loads((folder/'job.json').read_text('utf-8'))
        assert job['status']=='completed',job
        sequence=json.loads((folder/'sequence.json').read_text('utf-8'))
        assert sequence['status']=='completed' and len(sequence['frames'])==8
        assert len({entry['prompt_id'] for entry in sequence['frames']})==8
        assert len({digest(folder/entry['image']) for entry in sequence['frames']})==8
        assert state['progress']>0 and state['frame_ready']==8
        assert window.animation_player.timer.isActive()
        for entry in sequence['frames']:
            with Image.open(folder/entry['image']) as image:
                assert image.size==(768,1024) and image.mode=='RGBA'
            graph=json.loads((folder/entry['workflow']).read_text('utf-8'))
            assert graph['5']['inputs']['seed']==20261027
            if sequence['schema_version']>=2:
                assert entry['quality']['max_rgb_change']<=16
                assert entry['quality']['opaque_pixels']>20000
                assert 'blue bob' not in graph['2']['inputs']['text']
        with Image.open(folder/'walk.gif') as gif: assert gif.n_frames==8
        state['index']=window.animation_player.index; state['after']=time.monotonic()+.4; state['stage']='playback'
    elif state['stage']=='playback' and time.monotonic()>state['after']:
        assert window.animation_player.index!=state['index']
        window.animation_player.toggle(); assert not window.animation_player.timer.isActive()
        window.animation_player.slider.setValue(3); assert window.animation_player.index==3
        window.grab().save(str(DATA/'walk-studio.png'))
        window.animation_player.load(state['folder']/'sequence.json')
        window.open_assets(); assert window.assets_dialog.animations.count()>0; window.assets_dialog.close()
        record={'passed':True,'folder':str(state['folder']),'frames':8,'real_comfyui_jobs':8,
                'progress_events':state['progress'],'loop_playback':True,'scrubbing':True,
                'chinese_reach_binding':True,'sprite_sheet':str(state['folder']/'sprite_sheet.png'),
                'gif':str(state['folder']/'walk.gif')}
        write_json(DATA/'walk-acceptance.json',record); print(json.dumps(record),flush=True)
        state['stage']='exit'; window.animation_player.stop()
    elif state['stage']=='exit' and not window.workers and not window.current:
        app.exit(state['exit_code'])


def guarded():
    try: tick()
    except Exception as exc:
        print('FAIL',repr(exc),flush=True)
        if window.current: window.cancel_current()
        state['stage']='exit'; state['exit_code']=1; window.timer.stop()


timer=QTimer(); timer.timeout.connect(guarded); timer.start(150)
sys.exit(app.exec())
