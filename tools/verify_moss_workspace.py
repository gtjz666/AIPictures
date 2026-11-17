"""Real Qt workspace contract; optionally run one new native MOSS layout job."""
import argparse,json,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.moss_workspace import open_workspace
from aipictures.storage import write_json


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--live',action='store_true');a=p.parse_args()
 proof=a.output.resolve();proof.mkdir(parents=True,exist_ok=False);data=proof/'data';data.mkdir();c=json.loads(a.config.read_text('utf-8'));c.update(validated=True,validated_modes=['layout'])
 write_json(data/'moss-image-settings.json',c)
 app=create_application([])
 from PySide6.QtGui import QFontDatabase
 font=Path('C:/Windows/Fonts/msyh.ttc')
 if font.is_file():
  families=QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(font)))
  if families:app.setStyleSheet(app.styleSheet()+'\nQWidget { font-family: \"'+families[0]+'\"; }')
 with patch('aipictures.app.DATA',data),patch('aipictures.moss_workspace.DATA',data),patch('aipictures.gpu_watch_ui.attach'),patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
  w=Window();w.timer.stop();w.resize(1440,940);w.show();m=open_workspace(w);QTest.qWait(80)
  assert w.workbench.design_button.text()=='画面设计' and '画面设计' in m.windowTitle()
  w.grab().save(str(proof/'main-toolbar.png'))
  m.grab().save(str(proof/'layout-workspace.png'))
  original=m.prompt.toPlainText();m.busy=True
  called=[];w.pending=[({},dict(mode='h3_image',backend='standalone'),proof/'not-started',None)];w.h3_image_controller.start=lambda *_:called.append(True)
  w.start_next();assert not called and len(w.pending)==1
  w.pending.clear();m.busy=False
  if a.live:
   m.generate();assert m.busy
   m.prompt.setPlainText('这是排队后的新要求，不应改变刚才提交的任务。')
   started=time.monotonic()
   while m.busy and time.monotonic()-started<600:app.processEvents();time.sleep(.03)
   assert not m.busy and m.result_path,m.status.text()
   job=json.loads((m.folder/'job.json').read_text('utf-8'));assert job['status']=='completed' and job['params']['positive']==original
   assert m.progress.maximum()==100 and m.progress.value()==100
   m.grab().save(str(proof/'layout-result.png'));m.use_result();assert w.preview_path==str(m.result_path)
   write_json(proof/'live.json',dict(job=str(m.folder),result=str(m.result_path),snapshot_frozen=True,terminal_progress=True))
  write_json(proof/'ui-proof.json',dict(native_workspace=True,main_queue_serialized=True,layout_export_available=True,live=a.live))
  m.close();w.close();QTest.qWait(100)
 print('MOSS_WORKSPACE_QT_OK',flush=True)


if __name__=='__main__':main()
