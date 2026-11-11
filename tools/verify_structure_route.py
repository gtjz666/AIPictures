"""Native UI protocol checks; generated media and network are fixture-only."""
import json,tempfile,threading
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtTest import QTest
from PIL import Image
from aipictures.app import Window,create_application
from aipictures.structure_control import ADAPTER
from aipictures.storage import write_json
from tests.test_image_choice_retirement import model_info
from tools.verify_dock_workspace import wait_until


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);data=root/'data';data.mkdir()
        write_json(data/'structure-control-settings.json',dict(validated=True,python=__file__,weights=__file__,aux_source=str(root)))
        with patch('aipictures.app.DATA',data),patch('aipictures.storage.DATA',data),patch.object(Window,'auto_connect_engine'), \
                patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
            w=Window();w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(30)
            try:
                refs=[root/'source.png',root/'identity.png']
                for p in refs:Image.new('RGB',(24,24),'blue').save(p)
                w.reference_chat.import_images(refs);w.workbench.right_tabs.setCurrentIndex(1)
                w.positive.setPlainText('将图1中的人物替换为图2中的角色，保持图1的姿势和构图')
                w.workbench.prompt_output.setPlainText('An anime character, with geometry provided by the structure condition.')
                c=w.generation_intent;assert c.current() and '图1' in w.workbench.structure_note.text()
                w.workbench.structure_choice.setCurrentIndex(w.workbench.structure_choice.findData('off'))
                assert c.current() is None
                w.workbench.structure_choice.setCurrentIndex(0);assert c.current()
                info=model_info();info['LoraLoaderModelOnly']={'input':{'required':{'lora_name':[[ADAPTER]]}}}
                w.info=dict(object_info=info,nodes=list(info)+['CLIPTextEncode','LoadImage','SaveImage','VAEDecode']);w.connected=True
                write_json(data/'flux-klein-settings.json',dict(validated=True))
                w.output_background.setCurrentIndex(w.output_background.findData('opaque'))
                w.client=Mock();uploaded=[]
                def upload(p):uploaded.append(str(p));return 'server_'+p.name
                w.client.upload_image.side_effect=upload
                def extract(config,source,output,*_):
                    output.mkdir();path=output/'depth.png';Image.new('RGB',(512,512),'gray').save(path)
                    return dict(depth=str(path),device='cpu',source=str(source))
                with patch('aipictures.structure_control.extract',side_effect=extract),patch.object(w,'start_next'):
                    w.enqueue();wait_until(lambda:not w.preparing)
                    assert len(w.pending)==1,w.status.text()
                    graph,params,folder,_=w.pending.pop()
                    actual=json.loads((folder/'workflow.json').read_text('utf-8'))
                    assert actual==graph and actual['structure_adapter']['class_type']=='LoraLoaderModelOnly'
                    assert graph['image_1']['inputs']['image']=='server_depth.png'
                    assert len(uploaded)==2 and Path(uploaded[0]).name=='depth.png'
                    assert params['reference_policy']=='trained_depth_structure_v1'
                    assert (folder/'structure-control.json').is_file()
                started=threading.Event();release=threading.Event();uploaded.clear()
                def delayed(*args):started.set();assert release.wait(10);return extract(*args)
                with patch('aipictures.structure_control.extract',side_effect=delayed),patch.object(w,'start_next'):
                    w.enqueue();wait_until(started.is_set)
                    w.workbench.structure_choice.setCurrentIndex(w.workbench.structure_choice.findData('2'));release.set()
                    wait_until(lambda:not w.preparing)
                    assert not w.pending and '修改' in w.status.text()+w.intent_controller.note.text()+w.reference_chat.view.toPlainText()
                    assert c.current() is None and w.progress.maximum()==100
                w.workbench.select_category('long_video');assert not w.workbench.structure_row.isVisible()
            finally:w.close();QTest.qWait(40)
    print('Structure binding / actual queued graph / stale choice rejection: PASS',flush=True)


if __name__=='__main__':main()
