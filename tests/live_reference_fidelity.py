"""Real Qt preserve-reference image plus controlled high-denoise comparison."""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw
from PySide6.QtCore import QTimer

from aipictures.app import Window,create_application
from aipictures.reference_analysis import opaque_reference
from aipictures.storage import DATA,write_json
from aipictures.workflow_library import digest


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('reference'); args=parser.parse_args()
    reference=Path(args.reference).resolve(); source_digest=digest(reference)
    app=create_application([]); window=Window(); window.show()
    state={'stage':'connect','start':time.monotonic(),'code':0}
    def tick():
        if time.monotonic()-state['start']>1200: raise TimeoutError(state['stage'])
        if state['stage']=='failed': raise RuntimeError(state['error'])
        if state['stage']=='connect' and window.connected:
            window.timer.stop(); window.reset_graph(); window.set_reference(reference)
            window.seed.setText('20261027'); window.steps.setValue(24)
            assert window.preserving_reference()
            window.generate_button.click(); assert window.preparing
            state['stage']='preparing'
        elif state['stage']=='preparing' and window.current:
            state['folder']=window.current['folder']; state['stage']='generating'
        elif state['stage']=='generating' and not window.current:
            folder=state['folder']; job=json.loads((folder/'job.json').read_text('utf-8'))
            assert job['status']=='completed',job
            graph=json.loads((folder/'workflow.json').read_text('utf-8'))
            assert job['params']['reference_policy']=='preserve' and job['params']['denoise']<=.25
            assert not any(n['class_type'] in ('LoraLoader','ImageUpscaleWithModel') for n in graph.values())
            result=json.loads((folder/'result.json').read_text('utf-8'))
            state['preserved']=result['original_images'][0]
            state['image']=result['images'][0]
            comparison=folder/'high-denoise-comparison'; comparison.mkdir()
            sampler=graph[job['params']['bindings']['sampler']]['inputs']; sampler['denoise']=.6
            write_json(comparison/'workflow.json',graph)
            state['stage']='comparison'
            def finished(kind,data):
                if kind=='error': state['error']=data; state['stage']='failed'
                if kind=='result':
                    state['comparison']=data['images'][0]; state['stage']='review'
            window.launch(lambda emit:window.client.generate(graph,comparison,emit,threading.Event()),finished)
        elif state['stage']=='review':
            folder=state['folder']
            with Image.open(state['preserved']) as output: size=output.size
            with Image.open(reference) as image:
                rgba=image.convert('RGBA').resize(size,Image.Resampling.LANCZOS)
                original=opaque_reference(rgba).convert('RGB')
                mask=np.asarray(rgba.getchannel('A'))>240
            with Image.open(state['preserved']) as image: low=image.convert('RGB')
            with Image.open(state['comparison']) as image: high=image.convert('RGB')
            pixels=np.asarray(original,dtype=np.float32)
            low_error=float(np.abs(np.asarray(low,dtype=np.float32)-pixels)[mask].mean())
            high_error=float(np.abs(np.asarray(high,dtype=np.float32)-pixels)[mask].mean())
            # Pixel comparison is diagnostic; it does not certify identity or every detail.
            assert low_error<high_error,(low_error,high_error)
            preview=Image.new('RGB',(3*320,520),'white'); draw=ImageDraw.Draw(preview)
            for index,(label,image) in enumerate([('Reference',original),('Preserve / 0.25',low),('Redraw / 0.60',high)]):
                image=image.copy(); image.thumbnail((320,480),Image.Resampling.LANCZOS)
                preview.paste(image,(index*320+(320-image.width)//2,30))
                draw.text((index*320+12,8),label,fill='black')
            preview.save(folder/'fidelity-comparison.jpg')
            with Image.open(state['image']) as image:
                assert image.mode=='RGBA' and image.getpixel((0,0))[3]==0
            assert digest(reference)==source_digest
            record={'passed':True,'scope':'execution_and_source_pixel_deviation',
                'folder':str(folder),'source':str(reference),'source_unchanged':True,
                'reference_policy':'preserve','denoise':.25,'comparison_denoise':.6,
                'foreground_mean_absolute_rgb_error':{'preserve':round(low_error,3),'comparison':round(high_error,3)},
                'visual_review':{'accepted':False,'status':'manual_review_required'},
                'image':state['image'],'comparison':str(folder/'fidelity-comparison.jpg'),
                'elapsed_seconds':round(time.monotonic()-state['start'],1)}
            write_json(DATA/'reference-fidelity-image-acceptance.json',record)
            window.grab().save(str(folder/'studio-preview.png'))
            print(json.dumps(record,ensure_ascii=True),flush=True); state['stage']='exit'
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
