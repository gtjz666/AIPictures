"""Real Qt offline routing, sixteen slots, stale drafts and frozen jobs. No inference."""
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from aipictures.workflow_library import digest


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)),patch('aipictures.storage.DATA',Path(temp)), \
            patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        data=Path(temp);source=data/'engine';source.mkdir();(source/'main.py').write_text('')
        model=data/'model';model.write_bytes(b'test-only');paths=data/'paths';paths.write_text('')
        row=dict(path=str(model),bytes=model.stat().st_size,sha256=digest(model))
        import sys
        write_json(data/'h3-image-settings.json',dict(validated=True,python=sys.executable,source=str(source),model_paths=str(paths),models=[row,row],encoder=row))
        w=Window();w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(60)
        try:
            w.model_family.setCurrentIndex(w.model_family.findData('h3_image'));assert w.generate_button.isEnabled() and not w.connected
            refs=[]
            for n in range(1,17):
                p=data/f'{n}.png';Image.new('RGB',(40+n,80),(n*10,40,90)).save(p);refs.append(p)
            w.intent_controller.import_files(refs)
            assert set(w.reference_chat.references())==set(range(1,17)),w.status.text()
            assert w.workbench.reference_cells[16].isVisible()
            w.reference_chat.remove(2);assert 3 in w.reference_chat.references() and 2 not in w.reference_chat.references()
            w.positive.setPlainText('Edit Image 1 using the art style of Image 16, preserving the pose of Image 1.')
            w.workbench.right_tabs.setCurrentIndex(1)
            assert w.workbench.prepare_prompt.isVisible() and w.generate_button.isVisible()
            w.workbench.prompt_output.setPlainText(w.positive.toPlainText())
            w.negative.setPlainText('OLD HIDDEN NEGATIVE MUST NOT LEAK')
            assert w.generation_intent.current()
            with patch.object(w,'start_next') as start:
                assert w.h3_image_controller.intercept();assert start.call_count==1
            graph,params,folder,item=w.pending[0]
            assert '<Picture 15>' in params['positive'] and params['negative']==''
            assert len(params['references'])==15 and len([k for k in graph if k.startswith('image_')])==15
            assert params['requirement_contract']['source']['image_family']=='h3_image'
            assert all(digest(Path(row['path']))==row['sha256'] for row in params['references'].values())
            frozen=params['positive'];w.workbench.prompt_output.setPlainText('Different request')
            assert params['positive']==frozen
            w.clear_pending();w.positive.setPlainText('Changed source requirement')
            assert w.generation_intent.current() is None
            assert not w.workbench.structure_row.isVisible()
        finally:w.close();QTest.qWait(40)
    print('Qt sixteen references / offline engine / exact binding / hidden-negative isolation / frozen job / stale draft: PASS')


if __name__=='__main__':main()
