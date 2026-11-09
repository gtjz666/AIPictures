"""Native Qt reference conversation protocol; model and queue calls are fixtures."""
import json
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtTest import QTest
from aipictures.app import Window, create_application
from aipictures.storage import write_json
from tests.test_image_choice_retirement import model_info
from tools.verify_dock_workspace import wait_until


def main():
    app=create_application([])
    proof=Path('data/acceptance/reference-chat-20261109/ui').resolve();proof.mkdir(parents=True,exist_ok=True)
    info=model_info();calls=[];queued=[]
    with tempfile.TemporaryDirectory() as tmp, patch('aipictures.app.DATA',Path(tmp)), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
         patch('aipictures.intent_controller.settings',return_value={'name':'fixture'}), \
         patch('aipictures.flux_klein.enabled',return_value=True), \
         patch('aipictures.motion_native_backend.release_shared',return_value=[]):
        root=Path(tmp);paths=[]
        for i in range(4):
            path=root/f'fixture{i}.png';Image.new('RGB',(128,192),(40+i*40,70,150)).save(path);paths.append(path)
        w=Window();w.timer.stop();w.connected=True;w.client=SimpleNamespace(url='http://127.0.0.1:8188')
        w.info=dict(object_info=info,nodes=list(info),checkpoints=[],loras=[],samplers=['euler'],schedulers=['simple'])
        w.resize(1440,940);w.show();QTest.qWait(100)
        w.intent_controller.import_files(paths)
        refs=w.reference_chat.references()
        assert list(refs)==[1,2,3,4] and w.output is None and w.pixmap.isNull()
        assert w.intent_controller.input.isVisible() and w.intent_controller.organize.isVisible()
        assert not w.reference_chat.view.isVisible()
        assert w.intent_controller.organize.parent()!=w.workbench.prompt_page
        w.intent_controller.input.setPlainText('图1的人物，图2的姿势，图3和图4的画风。')
        def analyze(*args,**kwargs):
            calls.append(args[3])
            return dict(policy='numbered_references_v1',plan=dict(kind='image',summary='图1人物、图2姿势，融合图3图4画风',
                positive_prompt='Use identity from 图1, pose from 图2, styles from 图3 and 图4.',negative_prompt='',timeline=[],questions=[]))
        with patch('aipictures.multi_reference.analyze',side_effect=analyze):
            w.intent_controller.start(False);wait_until(lambda:not w.preparing)
        assert len(calls)==1 and list(calls[0])==[1,2,3,4], (calls,w.intent_controller.note.text(),w.status.text(),w.reference_chat.view.toPlainText())
        assert '图4' in w.positive.toPlainText() and '已更新提示词' in w.reference_chat.view.toPlainText()
        w.workbench.right_tabs.setCurrentWidget(w.workbench.reference_items);QTest.qWait(50)
        w.grab().save(str(proof/'four-references.png'))
        # Stable IDs and invalid references block submission before upload/queue.
        w.reference_chat.remove(2)
        assert list(w.reference_chat.references())==[1,3,4]
        try:w.reference_chat.snapshot()
        except ValueError as exc:assert '图2' in str(exc)
        else:raise AssertionError('Missing image was silently rebound')
        w.positive.setPlainText('Use identity from 图1 and styles from 图3 and 图4.')
        graph,params=w.reference_chat.snapshot()
        assert graph['guider']['inputs']['positive']==['pos_image_4',0]
        assert [r['model_input'] for r in params['references']]==[1,2,3]
        w.reference_chat.import_images([paths[1]],number=2)
        uploads=[]
        w.client.upload_image=lambda path:uploads.append(str(path)) or 'server/'+Path(path).name
        folder=root/'queued';folder.mkdir()
        with patch.object(w,'queue_graph',side_effect=lambda g,p:queued.append((g,p)) or folder),patch.object(w,'start_next'):
            assert w.reference_chat.intercept();wait_until(lambda:not w.preparing)
        assert len(uploads)==4 and len(queued)==1
        assert [queued[0][0][f'image_{i}']['inputs']['image'] for i in (1,2,3,4)]==[f'server/image_{i}.png' for i in (1,2,3,4)]
        assert w.output is None and w.pixmap.isNull()
        w.resize(1040,760);QTest.qWait(80);w.grab().save(str(proof/'compact.png'))
        write_json(proof/'acceptance.json',dict(native_qt=True,model_calls='fixtures',four_uploads=True,numbering_gaps_preserved=True,missing_ids_blocked=True,result_canvas_untouched=True))
        w.close();QTest.qWait(30)
    print('Native reference chat protocol passed.',flush=True)


if __name__=='__main__':main()
