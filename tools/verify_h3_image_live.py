"""Actual Qt -> optional local text translation -> native H3 Image, once per case."""
import argparse
import json
import shutil
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from aipictures.workflow_library import digest


def wait(condition,seconds):
    start=time.monotonic()
    while not condition():
        if time.monotonic()-start>seconds:raise TimeoutError('Inspect original job; no automatic resubmission')
        QTest.qWait(40);time.sleep(.01)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--machine',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);a=p.parse_args()
    root=a.proof.resolve();root.mkdir(parents=True,exist_ok=False);data=root/'isolated';data.mkdir()
    c=json.loads(a.machine.read_text('utf-8'));c.update(validated=True,validation_scope='isolated production acceptance, not installed')
    c['encoder']['sha256']='35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6'
    write_json(data/'h3-image-settings.json',c)
    shutil.copyfile(a.data/'local-intent-settings.json',data/'local-intent-settings.json')
    cases=json.loads(a.plan.read_text('utf-8'));write_json(root/'plan.json',cases)
    app=create_application([])
    with ExitStack() as cleanup,patch('aipictures.app.DATA',data),patch('aipictures.storage.DATA',data), \
            patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(100)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(80)
        w.model_family.setCurrentIndex(w.model_family.findData('h3_image'));w.workbench.right_tabs.setCurrentIndex(1)
        assert w.h3_image_controller.active() and not w.connected and w.generate_button.isEnabled()
        rows=[]
        for case in cases:
            for n in list(w.reference_chat.references()):w.reference_chat.remove(n)
            originals={p:digest(Path(p)) for p in case['references']}
            if case['references']:w.reference_chat.import_images([Path(p) for p in case['references']])
            assert len(w.reference_chat.references())==len(case['references']),w.status.text()
            assert not w.reference_chat.structural_binding() and not w.workbench.structure_row.isVisible()
            w.positive.setPlainText(case['requirement']);w.seed.setText(str(case['seed']))
            w.workbench.right_tabs.setCurrentIndex(1)
            assert w.workbench.prepare_prompt.isVisible() and w.generate_button.isVisible()
            if 'width' in case:w.width.setValue(case['width']);w.height.setValue(case['height'])
            w.output_background.setCurrentIndex(w.output_background.findData('preserve'))
            print('PREPARING',case['id'],w.width.value(),w.height.value(),flush=True)
            w.workbench.prepare_prompt.click();wait(lambda:not w.preparing,600)
            prepared=w.generation_intent.current();assert prepared and prepared['english'],w.status.text()
            assert not w.current and not w.pending,'prepare must not generate an image'
            assert not w.task_display.clock.isActive() and w.progress.maximum()==100
            write_json(root/(case['id']+'-prepared.json'),prepared);w.grab().save(str(root/(case['id']+'-prompt-ui.png')))
            print('GENERATING',case['id'],flush=True)
            before=set((data/'jobs').glob('*/job.json')) if (data/'jobs').exists() else set()
            w.generate_button.click();QTest.qWait(80);wait(lambda:not w.preparing and w.current is None and not w.pending,1800)
            created=set((data/'jobs').glob('*/job.json'))-before;assert len(created)==1,w.status.text()
            path=created.pop();job=json.loads(path.read_text('utf-8'));assert job['status']=='completed',job
            result=json.loads((path.parent/'result.json').read_text('utf-8'))
            for n in ('encode','sample','decode'):
                process=json.loads((path.parent/n/'process.json').read_text('utf-8'));assert process['status']=='stopped'
                assert process['returncode'] is not None
            assert all(digest(Path(p))==sha for p,sha in originals.items())
            assert not w.task_display.clock.isActive() and w.progress.maximum()==100 and w.progress.value()==100
            assert w.output==result['images'][0]
            shutil.copyfile(w.output,root/(case['id']+'-output.png'));w.grab().save(str(root/(case['id']+'-result-ui.png')))
            rows.append(dict(id=case['id'],job=str(path),result=result,original_hashes=originals,actual_qt=True,actual_models=True,separate_buttons=True,shared_engine_required=False))
            write_json(root/'acceptance.json',rows);print('COMPLETED',case['id'],flush=True)


if __name__=='__main__':main()
