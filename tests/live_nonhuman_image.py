"""Actual imported mascot -> pose-inapplicable fallback -> local reference generation."""
import json
import sys
import time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QTimer
from aipictures.app import Window,create_application
from aipictures.storage import DATA,write_json

app=create_application([]); window=Window(); window.show()
reference=Path(sys.argv[1]); state={'stage':'connect','start':time.monotonic(),'code':0}


def tick():
    if time.monotonic()-state['start']>900 and state['stage']!='exit': raise TimeoutError(state['stage'])
    if state['stage']=='connect' and window.connected:
        window.timer.stop(); window.apply_character(route='baseline'); window.set_reference(reference)
        window.generation_type.setCurrentIndex(0)
        window.reference_policy.setCurrentIndex(window.reference_policy.findData('redraw'))
        window.positive.setPlainText('参考图中的同一角色，自然站立，侧视，全身，保持一致')
        window.negative.setPlainText('多余手臂，多余腿部，颜色缺失，模糊，水印，文字')
        window.steps.setValue(20); window.seed.setText('20261027'); window.generate_button.click()
        assert window.preparing or window.current,window.chat_messages[-1]
        state['stage']='prepare'
    elif state['stage']=='prepare':
        if window.current: state['folder']=window.current['folder']; state['stage']='generate'
        elif not window.preparing: raise AssertionError(window.chat_messages[-1])
    elif state['stage']=='generate' and not window.current:
        folder=state['folder']; job=json.loads((folder/'job.json').read_text('utf-8'))
        assert job['status']=='completed',job
        assert job['params'].get('pose_fallback'),job['params']
        graph=json.loads((folder/'workflow.json').read_text('utf-8'))
        assert not any(node['class_type']=='ControlNetLoader' for node in graph.values())
        assert 'extra arms' in graph['3']['inputs']['text'] and 'watermark' in graph['3']['inputs']['text']
        with Image.open(window.output) as image:
            assert image.mode=='RGBA' and image.getpixel((0,0))[3]==0
        window.grab().save(str(DATA/'nonhuman-image-preview.png'))
        record={'passed':True,'folder':str(folder),'source':str(reference),'image':window.output,
            'pose_inapplicable_did_not_block_generation':True,'chinese_negative_mapped':True}
        write_json(DATA/'nonhuman-image-acceptance.json',record)
        print(json.dumps(record,ensure_ascii=True),flush=True); state['stage']='exit'
    elif state['stage']=='exit' and not window.workers: app.exit(state['code'])


def guarded():
    try: tick()
    except Exception as exc:
        print('FAIL',ascii(exc),flush=True)
        if window.current: window.cancel_current()
        state['stage']='exit'; state['code']=1; window.timer.stop()


timer=QTimer(); timer.timeout.connect(guarded); timer.start(150)
sys.exit(app.exec())
