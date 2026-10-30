"""A blocked model must neither block cancel dispatch nor prevent window/process exit."""
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.engine import ComfyClient


def main():
    app=create_application([])
    with tempfile.TemporaryDirectory() as temp,patch.object(Window,'connect_engine'), \
         patch.object(Window,'load_gallery'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
         patch('aipictures.app.DATA',Path(temp)),patch('subprocess.Popen') as popen:
        window=Window();window.timer.stop();window.show()
        client=ComfyClient();window.client=client
        release=threading.Event();late=[]
        window.launch(lambda emit:release.wait(60),lambda *args:late.append(args))
        window.current={'params':{'mode':'walk','action':'walk'},'folder':Path(temp),
                        'cancel':threading.Event(),'prompt_id':'owned'}
        window.task_display.start();window.progress.setRange(0,0)
        window.status.setText('编码参考与连续骨骼（采样前）')
        assert window.task_display.percent.text()!='0%'
        assert '采样前' in window.task_display.detail.text()
        requests=[]
        def request(path,body=None,**kwargs):
            requests.append((path,body,kwargs))
            return {'queue_running':[[0,'owned'],[1,'someone-else']]} if path=='/queue' and body is None else {}
        client.request=request;client._active.add('owned')
        window.cancel_button.click()
        deadline=time.monotonic()+1
        while not any(p=='/interrupt' for p,_,_ in requests) and time.monotonic()<deadline:QTest.qWait(20)
        assert any(p=='/interrupt' and body=={'prompt_id':'owned'} for p,body,_ in requests)
        assert all(options.get('timeout')==2 for _,_,options in requests)
        assert window.current['cancel'].is_set()
        began=time.monotonic();assert window.close()
        assert time.monotonic()-began<.25 and not window.isVisible()
        command=popen.call_args.args[0]
        assert 'aipictures.cancel_tasks' in command and 'owned' in command and 'someone-else' not in command
        release.set();QTest.qWait(100)
        assert not late,'Closing widgets must not receive late worker signals'
    print('Busy progress, independent owned cancellation, and immediate window close passed.')


def child_close():
    app=create_application([])
    with patch.object(Window,'connect_engine'),patch.object(Window,'load_gallery'), \
         patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        window=Window();window.timer.stop();window.show()
        def native_work(emit):
            if sys.platform=='win32':
                import ctypes
                ctypes.windll.kernel32.Sleep(60000)
            else:threading.Event().wait(60)
        window.launch(native_work,lambda *_:None)
        QTimer.singleShot(100,window.close)
        return app.exec()


if __name__=='__main__':
    if '--child' in sys.argv:raise SystemExit(child_close())
    main()
