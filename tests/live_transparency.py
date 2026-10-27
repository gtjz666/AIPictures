"""A real image job through the GUI, followed by CPU foreground segmentation."""
import json
import sys
import time
from PIL import Image
from PySide6.QtCore import QTimer
from aipictures.app import Window,create_application
from aipictures.storage import DATA,write_json
from aipictures.background import model_file

app=create_application([]); window=Window(); window.show()
state={'stage':'connect','start':time.monotonic(),'code':0,'postprocess':False}
launch=window.launch


def wrapped(action,callback):
    def event(kind,data):
        if kind=='postprocess': state['postprocess']=True
        callback(kind,data)
    launch(action,event)
window.launch=wrapped


def tick():
    if time.monotonic()-state['start']>600 and state['stage']!='exit': raise TimeoutError(state['stage'])
    if state['stage']=='connect' and window.connected:
        assert model_file().is_file(),str(model_file())
        window.timer.stop(); window.apply_character(route='baseline'); window.generation_type.setCurrentIndex(0)
        window.steps.setValue(24); window.seed.setText('20261027'); window.positive.setPlainText('全身，侧视，保持一致')
        window.generate_button.click(); state['stage']='upload'
    elif state['stage']=='upload' and window.current:
        state['folder']=window.current['folder']; state['stage']='generate'
    elif state['stage']=='generate' and not window.current:
        folder=state['folder']; job=json.loads((folder/'job.json').read_text('utf-8'))
        assert job['status']=='completed',job
        result=json.loads((folder/'result.json').read_text('utf-8'))
        assert result['background']['transparent'] and state['postprocess']
        with Image.open(result['images'][0]) as image:
            assert image.mode=='RGBA' and image.getpixel((0,0))[3]==0
            assert image.getchannel('A').getextrema()==(0,255)
            # Most background is removed; an actual opaque body remains.
            histogram=image.getchannel('A').histogram()
            assert histogram[0]>image.width*image.height*.5 and histogram[255]>20000
        with Image.open(result['original_images'][0]) as raw: assert raw.size==(768,1024)
        window.grab().save(str(DATA/'transparent-image-preview.png'))
        write_json(DATA/'transparency-acceptance.json',{'passed':True,'job':str(folder),
            'image':result['images'][0],'original':result['original_images'][0],
            'model':result['background']['model'],'background_corner_alpha':0,'foreground_opaque':True})
        print('Real single-image generation and transparent foreground output passed.',flush=True); state['stage']='exit'
    elif state['stage']=='exit' and not window.workers and not window.current: app.exit(state['code'])


def guard():
    try: tick()
    except Exception as exc:
        print('FAIL',repr(exc),flush=True); window.timer.stop(); window.cancel_current(); state['code']=1; state['stage']='exit'


timer=QTimer(); timer.timeout.connect(guard); timer.start(200)
sys.exit(app.exec())
