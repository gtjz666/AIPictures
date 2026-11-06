"""Check opt-in startup and task context in real Qt, without querying a GPU."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtTest import QTest
from aipictures.app import Window,create_application
from aipictures.gpu_watch_ui import attach
from aipictures.storage import write_json


def main():
    app=create_application([]);calls=[]
    with tempfile.TemporaryDirectory() as temp,patch('aipictures.app.DATA',Path(temp)), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'), \
         patch('aipictures.gpu_watch_ui.start',side_effect=lambda path:calls.append(path)):
        data=Path(temp);window=Window();window.timer.stop();window.show();QTest.qWait(30)
        attach(window);assert not calls and not hasattr(window,'gpu_watch_context_timer')
        write_json(data/'gpu-watch-settings.json',dict(enabled=True));attach(window)
        for _ in range(100):
            if calls:break
            QTest.qWait(20)
        assert calls==[data]
        window.current=dict(folder=data/'videos/job',params=dict(mode='video',prompt='private',api_key='private-key'))
        window.task_display.start();window.status.setText('模型采样中');window.progress.setValue(30)
        window.gpu_watch_context_timer.timeout.emit()
        context=json.loads((data/'gpu-watch-context.json').read_text('utf-8'))
        assert context['progress']==30 and context['state']=='running' and 'private' not in json.dumps(context)
        window.current=None;window.task_display.finish('completed');window.gpu_watch_context_timer.timeout.emit()
        context=json.loads((data/'gpu-watch-context.json').read_text('utf-8'))
        assert context['state']=='完成' and context['folder']==str(data/'videos/job')
        window.close();QTest.qWait(30)
    print('Optional recorder startup / real Qt task context / no GPU calls: PASS')


if __name__=='__main__':main()
