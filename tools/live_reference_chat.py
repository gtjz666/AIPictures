"""One real four-reference conversation and image generation through native Qt.

Use a new output folder. No automatic resubmission or rerolls.
"""
import argparse
import json
import shutil
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtTest import QTest
from aipictures.app import Window, create_application
from aipictures.engine import ComfyClient
from aipictures.image_family import restore
from aipictures.result_cache import ResultCache
from aipictures.storage import DATA, write_json


def wait(condition, timeout):
    deadline=time.monotonic()+timeout
    while not condition():
        if time.monotonic()>deadline:raise TimeoutError('Acceptance timed out; inspect original job, never auto-resubmit')
        QTest.qWait(80)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--reference',type=Path,action='append',required=True)
    p.add_argument('--brief',required=True)
    p.add_argument('--url',default='http://127.0.0.1:8188')
    p.add_argument('--settings-root',type=Path,default=DATA)
    args=p.parse_args();root=args.folder.resolve()
    if root.exists():raise ValueError('Existing evidence preserved; choose a new folder')
    if not 2<=len(args.reference)<=4:raise ValueError('Use 2–4 static references')
    client=ComfyClient(args.url);queue=client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):raise ValueError('Backend busy; not starting')
    info=client.discover();root.mkdir(parents=True)
    for name in ('flux-klein-settings.json','local-intent-settings.json'):
        shutil.copy2(args.settings_root/name,root/name)
    app=create_application([])
    with patch('aipictures.app.DATA',root),patch('aipictures.storage.DATA',root), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();w.timer.stop();w.cache_store=ResultCache(root)
        w.client=client;w.connected=True;w.info=info
        restore(w);w.model_family.setCurrentIndex(w.model_family.findData('auto'))
        w.reference_chat.import_images(args.reference)
        if len(w.reference_chat.references())!=len(args.reference):raise ValueError(w.reference_chat.view.toPlainText())
        w.width.setValue(512);w.height.setValue(768)
        w.output_background.setCurrentIndex(w.output_background.findData('preserve'))
        if w.output_background.currentIndex()<0:w.output_background.setCurrentIndex(0)
        w.seed_mode.setCurrentIndex(w.seed_mode.findData('fixed'));w.seed.setText('20261109')
        w.resize(1440,940);w.show();QTest.qWait(100)
        w.intent_controller.input.setPlainText(args.brief)
        print('Starting explicit four-image observation and planning',flush=True)
        w.intent_controller.start(False)
        wait(lambda:not w.preparing,1500)
        if not w.intent_controller.applied:raise ValueError(w.reference_chat.view.toPlainText())
        write_json(root/'reviewed-prompts.json',dict(positive=w.positive.toPlainText(),negative=w.negative.toPlainText(),brief=args.brief))
        w.grab().save(str(root/'before-generation.png'))
        print('Planning complete; starting one frozen multi-reference generation',flush=True)
        w.enqueue()
        wait(lambda:not w.preparing and w.current is None and not w.pending,1800)
        if not w.output:raise ValueError(w.reference_chat.view.toPlainText()+'\n'+w.status.text())
        w.grab().save(str(root/'generated-ui.png'))
        write_json(root/'acceptance.json',dict(actual_models=True,output=w.output,reference_count=len(args.reference),
                   assistant_folder=str(w.intent_controller.current_record),precision_review_pending=True))
        print('Completed: '+w.output,flush=True)
        w.close();QTest.qWait(50)


if __name__=='__main__':main()
