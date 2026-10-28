"""Real UI -> automatic complete skeleton -> normal 20-step inference -> transparent export."""
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
    parser=argparse.ArgumentParser(); parser.add_argument('--wait-for'); args=parser.parse_args()
    app=create_application([]); window=Window(); window.show()
    state={'stage':'connect','started':time.monotonic(),'code':0,'events':0,'frames':0,'ticks':0}
    original_launch=window.launch
    def launch(action,callback):
        def event(kind,data):
            if kind=='pose_video_event' and data['event']=='progress':
                state['events']+=1
                print('Pose studio progress',data['data']['value'],'/',data['data']['max'],flush=True)
                if state['events']==7: window.grab().save(str(DATA/'task-progress-live.png'))
            if kind=='frame_ready': state['frames']+=1
            callback(kind,data)
        original_launch(action,event)
    window.launch=launch
    def tick():
        state['ticks']+=1
        if time.monotonic()-state['started']>7200: raise TimeoutError(state['stage'])
        if state['stage']=='connect' and window.connected:
            if args.wait_for and not Path(args.wait_for).is_file(): return
            window.timer.stop(); window.generation_type.setCurrentIndex(1)
            source=DATA/'references/be93d02d63944509ba617f5c90021bd0.png'; window.set_reference(source)
            assert window.animation_engine.currentData()=='animate' and window.motion_mode.currentData()=='auto'
            assert '左右腿交替' in window.positive.toPlainText()
            # Deliberately omit action keywords: selecting the type must be sufficient.
            window.positive.setPlainText('参考图中的同一角色，全身，保持一致')
            window.seed.setText('20261029'); window.animation_steps.setValue(20)
            window.generate_button.click(); assert window.current,window.chat_messages[-1]
            state['folder']=window.current['folder']; state['stage']='generation'
            print('Pose studio folder:',state['folder'],flush=True)
        elif state['stage']=='generation' and window.current is None:
            folder=state['folder']; job=json.loads((folder/'job.json').read_text('utf-8'))
            assert job['status']=='completed',job
            manifest=json.loads((folder/'sequence.json').read_text('utf-8'))
            assert manifest['method']=='wan_animate_pose_sequence'
            assert len(manifest['frames'])==8 and state['frames']==8 and state['events']==20
            assert len(list((folder/'poses').glob('pose_*.json')))==17
            assert manifest['pose_selection']['source_indices']==list(range(0,16,2))
            graph=json.loads((folder/'video/workflow.json').read_text('utf-8'))
            assert graph['8']['class_type']=='WanAnimateToVideo' and graph['8']['inputs']['pose_video']
            assert '左右腿交替' in graph['5']['inputs']['text']
            assert graph['11']['inputs']['cfg']==1 and 'acceleration' not in graph
            assert len({digest(folder/item['image']) for item in manifest['frames']})==8
            for item in manifest['frames']:
                assert (folder/item['pose']).is_file()
                assert (folder/Path(item['pose']).parent/'feet.png').is_file()
                with Image.open(folder/item['image']) as image:
                    assert image.mode=='RGBA' and image.size==(768,1024) and image.getpixel((0,0))[3]==0
            assert window.progress.value()==100 and window.task_display.percent.text()=='100%'
            assert window.status.text()=='走路动画 · 完成'
            assert folder.name not in window.queue_list.item(window.queue_list.count()-1).text()
            assert window.animation_player.timer.isActive()
            window.animation_player.stop(); window.grab().save(str(folder/'studio-preview.png'))
            record={'functional_execution_passed':True,'visual_review':'pending','folder':str(folder),
                'automatic_complete_skeleton':True,'manual_editing_required':False,'pose_files':17,'frames':8,
                'action_words_omitted_in_user_prompt':True,'action_macro_in_actual_workflow':True,
                'entire_cycle_exported':True,'left_task_name_and_percentage':True,'task_id_hidden':True,
                'elapsed_seconds':round(time.monotonic()-state['started'],1),'qt_ticks':state['ticks']}
            write_json(DATA/'pose-studio-acceptance.json',record); write_json(folder/'acceptance.json',record)
            print(json.dumps(record,ensure_ascii=True),flush=True); state['stage']='exit'
        elif state['stage']=='exit' and not window.workers: app.exit(state['code'])
    def guarded():
        try: tick()
        except Exception as exc:
            print('FAIL',repr(exc),flush=True)
            if window.current: window.cancel_current()
            window.timer.stop(); state['stage']='exit'; state['code']=1
    timer=QTimer(); timer.timeout.connect(guarded); timer.start(150)
    return app.exec()


if __name__=='__main__': sys.exit(main())
