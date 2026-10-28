"""Real Qt -> manual LoRA + manual restoration -> local RGBA generation."""
import json
import sys
import time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer
from aipictures.app import Window,create_application
from aipictures.lora_catalog import entry_for
from aipictures.storage import DATA,write_json


def main():
    app=create_application([]); window=Window(); window.show()
    state={'stage':'connect','start':time.monotonic(),'ticks':0,'code':0}
    def tick():
        state['ticks']+=1
        if time.monotonic()-state['start']>1200: raise TimeoutError(state['stage'])
        if state['stage']=='connect' and window.connected:
            window.timer.stop()
            assert window.reference_path is None and window.pixmap.isNull()
            window.lora_category.setCurrentText('动漫')
            index=next(i for i in range(1,window.lora.count()) if entry_for(window.lora.itemData(i))['id']=='ghibli')
            window.lora.setCurrentIndex(index)
            window.positive.setPlainText('单个人物，动漫，蓝色头发，短发，白色衬衫，侧视，全身，轮廓清晰，背景简洁')
            window.negative.setPlainText('模糊，水印，文字，多余手臂，多余腿部，多余手指，多个人物，重复人物，人物设定图，三视图，多视图，画面分格，拼贴，多余道具')
            window.width.setValue(768); window.height.setValue(1024); window.steps.setValue(24)
            window.seed.setText('20261028'); window.quality_mode.setCurrentIndex(window.quality_mode.findData('anime'))
            window.generate_button.click(); assert window.current,window.chat_messages[-1]
            state['folder']=window.current['folder']; state['stage']='generation'
        elif state['stage']=='generation' and window.current is None:
            folder=state['folder']; job=json.loads((folder/'job.json').read_text('utf-8'))
            assert job['status']=='completed',job
            graph=json.loads((folder/'workflow.json').read_text('utf-8'))
            assert not any(n['class_type']=='LoadImage' for n in graph.values())
            loras=[n for n in graph.values() if n['class_type']=='LoraLoader']
            assert len(loras)==1 and entry_for(loras[0]['inputs']['lora_name'])['id']=='ghibli'
            assert any(n['class_type']=='ImageUpscaleWithModel' for n in graph.values())
            assert job['params']['reference'] is None
            assert job['params']['lora_style']['id']=='ghibli'
            result=json.loads((folder/'result.json').read_text('utf-8'))
            assert result['background']['edge_smoothing']
            with Image.open(window.output) as image:
                assert image.mode=='RGBA' and image.size==(768,1024)
                alpha=np.asarray(image.getchannel('A'))
                assert alpha[0,0]==0 and (alpha>200).sum()>1000
                assert ((alpha>0)&(alpha<255)).sum()>100
            assert window.preview_role=='result' and window.preview_path==window.output
            assert state['ticks']>30 and window.preview.clickable
            window.grab().save(str(DATA/'styled-image-studio.png'))
            write_json(DATA/'style-image-acceptance.json',{'passed':True,'folder':str(folder),
                'manual_lora':'ghibli','manual_quality':'anime','no_reference_loaded_or_submitted':True,
                'real_lora_and_upscale_nodes':True,'transparent_antialiased_png':True,'qt_timer_ticks':state['ticks'],
                'elapsed_seconds':round(time.monotonic()-state['start'],1)})
            print('Manual LoRA + restoration + empty reference real Qt image generation passed.',flush=True)
            state['stage']='exit'
        elif state['stage']=='exit' and not window.workers: app.exit(state['code'])
    def guarded():
        try: tick()
        except Exception as exc:
            print('FAIL',repr(exc),flush=True)
            if window.current: window.cancel_current()
            window.timer.stop(); state['stage']='exit'; state['code']=1
    timer=QTimer(); timer.timeout.connect(guarded); timer.start(100)
    return app.exec()


if __name__=='__main__': sys.exit(main())
