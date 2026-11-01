"""Opt-in real Qt -> offline translation -> SDXL -> preview/save acceptance check."""
import argparse
import json
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from aipictures.app import Window, create_application
from aipictures.engine import ComfyClient
from aipictures.local_translation import settings
from aipictures.storage import DATA, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Use a new acceptance directory; existing jobs must not be resubmitted.')
    config = settings(DATA)
    if not config:
        raise ValueError('Install and configure the offline translator first.')
    client = ComfyClient()
    queue = client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):
        raise RuntimeError('Shared backend busy; no UI inference started.')
    info = client.discover()
    output.mkdir(parents=True)
    write_json(output/'translator-settings.json', config)
    app = create_application([])
    messages = []
    with patch('aipictures.app.DATA', output), patch.object(Window, 'connect_engine'), \
         patch.object(Window, 'load_gallery'), patch.object(Window, 'restore_chat'), \
         patch.object(Window, 'refresh_stats'), patch.object(QMessageBox, 'warning',
                 side_effect=lambda *args: messages.append(str(args[-1]))):
        window = Window()
        window.timer.stop()
        window.client, window.info, window.connected = client, info, True
        window.model.addItems(info['checkpoints'])
        window.model.setCurrentText(next(n for n in info['checkpoints'] if 'Juggernaut-XL_v9_' in n))
        window.sampler.addItems(info['samplers']); window.sampler.setCurrentText('dpmpp_2m')
        window.scheduler.addItems(info['schedulers']); window.scheduler.setCurrentText('karras')
        window.seed.setText('907013')
        window.positive.setPlainText('单个游戏道具，玻璃小瓶中装有红色发光药水，软木塞封口。等距视角，物件居中，浅灰色背景，轮廓清晰。')
        window.negative.setPlainText('多个瓶子，模糊，水印，文字')
        window.translate_prompt.setChecked(True)
        started = time.monotonic()
        window.enqueue()
        deadline = started+300
        while time.monotonic()<deadline and (window.current or window.preparing or window.pending or window.workers):
            app.processEvents()
            time.sleep(.01)
        folders = list((output/'jobs').glob('*'))
        if messages or len(folders)!=1:
            window.close()
            raise AssertionError(str(messages) or 'Expected one real UI job.')
        folder = folders[0]
        job = json.loads((folder/'job.json').read_text('utf-8'))
        if job['status']!='completed':
            window.close()
            raise AssertionError('UI job incomplete; receipt retained in '+str(folder))
        translated = json.loads((folder/'translation.json').read_text('utf-8'))
        graph = json.loads((folder/'workflow.json').read_text('utf-8'))
        assert translated['positive'] in graph['2']['inputs']['text']
        assert window.output and Path(window.output).is_file() and not window.pixmap.isNull()
        write_json(output/'acceptance.json', {'status':'passed','real_inference':True,
            'qt_translation_queue_preview_saved':True,'seconds':round(time.monotonic()-started,2),
            'job':str(folder),'image':str(window.output),'visual_review':'required'})
        window.close()
    print('REAL_TRANSLATED_UI_COMPLETE', str(folder), flush=True)


if __name__ == '__main__':
    main()
