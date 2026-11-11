"""Real Qt prompt preparation and production through the trained geometry route."""
import argparse,json,shutil
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.engine import ComfyClient
from aipictures.storage import write_json
from aipictures.reference_prompt import standalone
from aipictures.workflow_library import digest
from tools.verify_dock_workspace import wait_until


def main():
    p=argparse.ArgumentParser();p.add_argument('--proof',type=Path,required=True);p.add_argument('--data',type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--identity',type=Path);p.add_argument('--job',type=Path)
    p.add_argument('--reuse-subject-cache',type=Path);args=p.parse_args()
    frozen=json.loads((args.job/'job.json').read_text('utf-8'))['params'] if args.job else None
    refs={r['number']:Path(r['source']) for r in frozen['references']} if frozen else {1:args.source,2:args.identity}
    if any(p is None for p in refs.values()):raise ValueError('Provide --job or both --source and --identity')
    root=args.proof.resolve();root.mkdir(parents=True,exist_ok=False);data=root/'isolated';data.mkdir()
    for name in ('local-intent-settings.json','flux-klein-settings.json','structure-control-settings.json','background-settings.json'):
        shutil.copyfile(args.data/name,data/name)
    if args.reuse_subject_cache:
        cache=data/'reference-preparation';cache.mkdir()
        for path in args.reuse_subject_cache.glob('*'):
            if path.is_file() and path.suffix in ('.png','.json'):shutil.copyfile(path,cache/path.name)
        write_json(root/'cache-source.json',dict(source=str(args.reuse_subject_cache.resolve()),reused=True))
    client=ComfyClient();queue=client.request('/queue')
    if queue['queue_running'] or queue['queue_pending']:raise ValueError('Backend busy; no test submitted')
    info=client.discover();app=create_application([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    originals={str(p):digest(p) for p in refs.values()}
    with ExitStack() as cleanup,patch('aipictures.app.DATA',data),patch('aipictures.storage.DATA',data), \
            patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(50)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(50)
        w.client=client;w.info=info;w.connected=True;w.width.setValue(512);w.height.setValue(512);w.seed.setText('20261111')
        w.output_background.setCurrentIndex(w.output_background.findData('opaque'))
        w.reference_chat.import_images(list(refs.values()));w.workbench.right_tabs.setCurrentIndex(1)
        requirement=frozen['source_brief'] if frozen else '将图1中的人物替换为图2中的角色，保持图1的姿势和构图'
        w.positive.setPlainText(requirement);w.generation_type_changed()
        binding=w.reference_chat.structural_binding();assert binding and w.workbench.structure_row.isVisible()
        w.width.setValue(frozen['width'] if frozen else 512);w.height.setValue(frozen['height'] if frozen else 512)
        w.seed.setText(str(frozen['seed'] if frozen else 20261111))
        with patch.object(w,'enqueue') as submit:
            w.workbench.prepare_prompt.click();wait_until(lambda:not w.preparing,seconds=600)
            assert submit.call_count==0
        prepared=w.generation_intent.current();assert prepared,w.status.text()
        assert standalone(prepared['positive']) and prepared['english'] and standalone(prepared['english']['positive'])
        assert prepared['source']['requirement']==requirement
        record=json.loads(Path(prepared['record']).read_text('utf-8'))
        assert set(record['observations'])=={str(binding['identity'])} and record['engine_released']
        assert record['subject_preparation']['worker_returncode']==0
        w.grab().save(str(root/'prompt-ui.png'));write_json(root/'prepared.json',prepared)
        print('Actual prompt prepared; submitting separate image action',flush=True)
        w.generate_button.click();QTest.qWait(80)
        wait_until(lambda:not w.preparing and w.current is None and not w.pending,seconds=600)
        jobs=list((data/'jobs').glob('*/job.json'));assert len(jobs)==1,(w.status.text(),jobs)
        job=json.loads(jobs[0].read_text('utf-8'));assert job['status']=='completed',job
        graph=json.loads((jobs[0].parent/'workflow.json').read_text('utf-8'))
        assert graph['structure_adapter']['class_type']=='LoraLoaderModelOnly'
        assert graph['release' if 'release' in graph else 'guider']['inputs']['model']==['structure_adapter',0]
        evidence=json.loads((jobs[0].parent/'structure-control.json').read_text('utf-8'))
        assert evidence['evidence']['device']=='cpu' and evidence['evidence']['worker_returncode']==0
        assert evidence['subject_preparation']['cache_hit'] and evidence['subject_preparation']['device']=='cpu'
        result=json.loads((jobs[0].parent/'result.json').read_text('utf-8'))
        assert all(digest(Path(p))==sha for p,sha in originals.items())
        assert not w.task_display.clock.isActive() and w.progress.maximum()==100
        w.grab().save(str(root/'result-ui.png'))
        write_json(root/'acceptance.json',dict(actual_qt=True,actual_prompt_model=True,actual_image_model=True,
            separate_buttons=True,geometry_not_captioned=True,adapter_survives_queue=True,depth_worker_exited=True,
            original_hashes=originals,job=str(jobs[0]),evidence=evidence,result=result,visual_review_required=True))
    print('Actual structure-controlled UI generation: PASS',flush=True)


if __name__=='__main__':main()
