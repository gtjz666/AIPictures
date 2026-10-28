"""Real Qt -> Wan2.2 14B -> transparent frames. Downloads must already be approved/installed."""
import argparse
import json
import sys
import time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QTimer
from aipictures.app import Window,create_application
from aipictures.storage import DATA,write_json
from aipictures.workflow_library import digest


def main():
    parser=argparse.ArgumentParser()
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--reference'); source.add_argument('--text')
    parser.add_argument('--steps',type=int,default=20)
    args=parser.parse_args()
    app=create_application([]); window=Window(); window.show()
    state={'stage':'connect','start':time.monotonic(),'progress':0,'ready':0,'code':0}
    launch=window.launch
    def tracked(action,callback):
        def event(kind,data):
            if kind=='video_event' and data['event']=='progress':
                state['progress']+=1
                print('Temporal progress',data['data']['value'],'/',data['data']['max'],flush=True)
            if kind=='frame_ready': state['ready']+=1
            callback(kind,data)
        launch(action,event)
    window.launch=tracked
    def tick():
        if time.monotonic()-state['start']>7200 and state['stage']!='exit': raise TimeoutError(state['stage'])
        if state['stage']=='connect' and window.connected:
            window.timer.stop(); window.generation_type.setCurrentIndex(1)
            if args.reference:
                window.set_reference(args.reference)
                window.positive.setPlainText('参考图中的同一角色，自然站立，侧视，全身，保持一致')
            else:
                window.animation_source.setCurrentIndex(1); window.positive.setPlainText(args.text)
            window.animation_steps.setValue(args.steps); window.seed.setText('20261027')
            window.negative.setPlainText('多余手臂，多余腿部，重复人物，颜色缺失，模糊，重影，文字，水印，复杂背景')
            window.generate_button.click()
            assert window.current,window.chat_messages[-1]
            state['folder']=window.current['folder']; state['stage']='generation'
            print('Animation folder:',state['folder'],flush=True)
        elif state['stage']=='generation' and not window.current:
            folder=state['folder']; job=json.loads((folder/'job.json').read_text('utf-8'))
            assert job['status']=='completed',job
            manifest=json.loads((folder/'sequence.json').read_text('utf-8'))
            assert manifest['status']=='completed' and len(manifest['frames'])==8
            assert state['progress']>0 and state['ready']==8
            assert len({digest(folder/item['image']) for item in manifest['frames']})==8
            graph=json.loads((folder/'video'/'workflow.json').read_text('utf-8'))
            assert graph['6']['inputs']['text']==window.negative.toPlainText()
            assert '走路' in graph['5']['inputs']['text']
            assert not any(node['class_type']=='DWPreprocessor' for node in graph.values())
            for item in manifest['frames']:
                with Image.open(folder/item['image']) as image:
                    assert image.mode=='RGBA' and image.size==(768,1024)
                    assert image.getpixel((0,0))[3]==0
                    assert sum(image.getchannel('A').histogram()[200:])>20000
            if args.reference: assert manifest['reference_sha256']==digest(args.reference)
            else:
                assert manifest['character_prompt_id'] and job['params']['reference'] is None
            assert window.animation_player.timer.isActive()
            window.grab().save(str(folder/'studio-preview.png'))
            record={'passed':False,'functional_execution_passed':True,
                'visual_review':{'accepted':False,'status':'manual_review_required'},
                'folder':str(folder),'reference_input':args.reference,'text_input':args.text,
                'backend':'wan22_14b','frames':8,'progress_events':state['progress'],
                'selected_action_overrides_standing_prompt':True,'native_chinese_negative':True,
                'human_detector_not_required':True,'manifest':str(folder/'sequence.json'),
                'elapsed_seconds':round(time.monotonic()-state['start'],1)}
            suffix='reference' if args.reference else 'text'
            write_json(DATA/f'temporal-{suffix}-acceptance.json',record)
            write_json(folder/'acceptance.json',record)
            print(json.dumps(record,ensure_ascii=True),flush=True)
            window.animation_player.stop(); state['stage']='exit'
        elif state['stage']=='exit' and not window.workers and not window.current: app.exit(state['code'])
    def guarded():
        try: tick()
        except Exception as exc:
            print('FAIL',ascii(exc),flush=True)
            if window.current: window.cancel_current()
            state['stage']='exit'; state['code']=1; window.timer.stop()
    timer=QTimer(); timer.timeout.connect(guarded); timer.start(200)
    return app.exec()


if __name__=='__main__': sys.exit(main())
