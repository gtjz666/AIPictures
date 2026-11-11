"""Explicit real per-image prompt preparation and optional single FLUX result."""
import argparse
import json
import shutil
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.engine import ComfyClient
from aipictures.motion_native_backend import release_shared
from aipictures.reference_prompt import standalone
from aipictures.storage import write_json
from aipictures.workflow import ImageRequest
from aipictures.flux_klein import UNET
from aipictures.multi_reference import build
from tools.verify_dock_workspace import wait_until


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,required=True);parser.add_argument('--proof',type=Path,required=True)
    parser.add_argument('--reference',type=Path,nargs='+',required=True);parser.add_argument('--render',action='store_true');args=parser.parse_args()
    root=args.proof.resolve();root.mkdir(parents=True,exist_ok=False);data=root/'isolated';data.mkdir()
    for path in args.data.glob('*settings.json'):shutil.copyfile(path,data/path.name)
    client=ComfyClient('http://127.0.0.1:8188');queue=client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):raise ValueError('Existing backend queue is busy; no test submitted.')
    release_shared(dict(url=client.url),cancel=threading.Event())
    app=create_application([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    requirement='将图1的人物美术风格修改为图2的美术风格，保留图1的人物动作与人物外形'
    with ExitStack() as cleanup,patch('aipictures.app.DATA',data),patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(50)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(40)
        w.reference_chat.import_images(args.reference);w.workbench.right_tabs.setCurrentIndex(1);w.positive.setPlainText(requirement)
        assert w.intent_controller.config and len(w.reference_chat.references())==2
        with patch.object(w,'enqueue') as submit:
            w.workbench.prepare_prompt.click();wait_until(lambda:not w.preparing,seconds=600)
            assert submit.call_count==0
        value=w.generation_intent.current();assert value,w.status.text()
        assert standalone(value['positive']) and value['negative']=='' and value['source']['requirement']==requirement
        assert w.workbench.prompt_output.toPlainText()==value['positive'] and not w.task_display.clock.isActive() and w.progress.maximum()==100
        assert not w.generation_intent.intercept()
        w.grab().save(str(root/'prompt-ui.png'))
        refs=w.reference_chat.references();positive=value.get('english',{}).get('positive') or value['positive']
        assert standalone(positive)
        write_json(root/'prepared.json',value)
        record=dict(explicit_button=True,automatic_image_submission=False,editable_prompt_below=True,reference_count=len(refs),standalone_chinese=True,standalone_engine_text=True,progress_finishes=True,raw_requirement_preserved=True)
        if args.render:
            info=client.request('/object_info');uploads={n:client.upload_image(p) for n,p in refs.items()}
            req=ImageRequest(UNET,positive,'',512,768,4,1.,20261111,'euler','flux2');graph,_=build(req,info,uploads)
            render=root/'image';render.mkdir();write_json(render/'workflow.json',graph)
            record['image']=client.generate(graph,render,lambda kind,value:print(kind,flush=True) if kind in ('queued','completed') else None,threading.Event())
            release_shared(dict(url=client.url),cancel=threading.Event())
        write_json(root/'acceptance.json',record)
    print('Real independent image observations / standalone prompt / explicit review: PASS',flush=True)


if __name__=='__main__':main()
