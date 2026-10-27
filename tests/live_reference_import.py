"""Real import of another character, adaptive pose preparation and actual single-image inference."""
import argparse
import json
import sys
import time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QTimer
from aipictures.app import Window,create_application
from aipictures.character_profile import load_profile
from aipictures.storage import DATA,write_json
from aipictures.workflow_library import digest

parser=argparse.ArgumentParser(); parser.add_argument('reference',type=Path)
reference=parser.parse_args().reference.resolve(); original_hash=digest(reference)
app=create_application([]); window=Window(); window.show()
state={'stage':'connect','start':time.monotonic(),'code':0}


def tick():
    if time.monotonic()-state['start']>900 and state['stage']!='exit': raise TimeoutError(state['stage'])
    if state['stage']=='connect' and not window.connected and not window.workers and time.monotonic()-state.get('retry',state['start'])>10:
        state['retry']=time.monotonic(); window.connect_engine()
    if state['stage']=='connect' and window.connected:
        window.timer.stop(); window.apply_character(route='baseline')
        window.set_reference(reference); window.generation_type.setCurrentIndex(0)
        if original_hash!=load_profile()['source_sha256']: assert window.reference_character and window.character_profile is None
        window.steps.setValue(24); window.seed.setText('20261027'); window.positive.setPlainText('站立，全身，侧视，保持一致')
        graph,params=window.graph_snapshot('__reference__')
        assert params['adaptive_action']=='stand'
        assert 'navy-blue bob hair' not in graph['2']['inputs']['text']
        assert 'reference' in graph['2']['inputs']['text']
        window.generate_button.click(); state['stage']='prepare'
    elif state['stage']=='prepare' and window.current:
        state['folder']=window.current['folder']; state['stage']='generate'
        print('Imported reference job:',state['folder'],flush=True)
    elif state['stage']=='prepare' and not window.preparing and not window.pending:
        raise RuntimeError(window.chat_messages[-1]['text'])
    elif state['stage']=='generate' and not window.current:
        folder=state['folder']; job=json.loads((folder/'job.json').read_text('utf-8'))
        assert job['status']=='completed',job
        params=job['params']; assert params['reference_analysis']['source_sha256']==original_hash
        assert params['adaptive_action']=='stand'
        graph=json.loads((folder/'workflow.json').read_text('utf-8'))
        assert graph['21']['inputs']['image']!='__adaptive_pose__' and graph['30']['inputs']['image']!='__adaptive_guide__'
        assert digest(reference)==original_hash
        with Image.open(window.output) as image:
            assert image.size==(768,1024) and image.mode=='RGBA'
            assert image.getpixel((0,0))[3]==0 and image.getchannel('A').histogram()[255]>20000
        window.grab().save(str(DATA/'imported-reference-preview.png'))
        write_json(DATA/'reference-import-acceptance.json',{'passed':True,'reference':str(reference),
            'source_sha256':original_hash,'job':str(folder),'reference_unmodified':True,
            'adaptive_pose_bound':True,'guide_bound':True,'transparent_output':True})
        print('Real imported-character reference, adaptive pose and transparent generation passed.',flush=True)
        window.apply_character(route='baseline'); state['stage']='exit'
    elif state['stage']=='exit' and not window.workers and not window.current: app.exit(state['code'])


def guard():
    try: tick()
    except Exception as exc:
        print('FAIL',repr(exc),flush=True); window.timer.stop(); window.cancel_current(); state['code']=1; state['stage']='exit'


timer=QTimer(); timer.timeout.connect(guard); timer.start(200)
sys.exit(app.exec())
