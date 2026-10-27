"""Validate the finished local sequence in all three preview views, without regenerating."""
import json
import sys
import time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QTimer
from aipictures.app import Window,create_application
from aipictures.storage import DATA,write_json

app=create_application([]); window=Window(); window.show()
record=json.loads((DATA/'walk-acceptance.json').read_text('utf-8')); folder=Path(record['folder'])
state={'stage':'connect','start':time.monotonic(),'code':0}


def tick():
    if time.monotonic()-state['start']>60: raise TimeoutError(state['stage'])
    if state['stage']=='connect' and window.connected:
        window.timer.stop(); window.generation_type.setCurrentIndex(1)
        window.animation_player.load(folder/'sequence.json')
        window.animation_player.toggle()
        assert window.sequence_preview.frames.count()==8
        window.sequence_preview.setCurrentIndex(1); state['after']=time.monotonic()+.5; state['stage']='frames'
    elif state['stage']=='frames' and time.monotonic()>state['after']:
        window.grab().save(str(DATA/'walk-all-frames.png'))
        window.sequence_preview.setCurrentIndex(2); state['after']=time.monotonic()+.5; state['stage']='sheet'
    elif state['stage']=='sheet' and time.monotonic()>state['after']:
        window.grab().save(str(DATA/'walk-sheet-preview.png'))
        assert not window.sequence_preview.sheet.pixmap().isNull()
        window.sequence_preview.select_frame(window.sequence_preview.frames.item(5))
        assert window.animation_player.index==5 and window.sequence_preview.currentIndex()==0
        window.grab().save(str(DATA/'walk-playback-preview.png'))
        for path in sorted(folder.glob('frame_*.png'))+[folder/'sprite_sheet.png']:
            with Image.open(path) as image:
                assert image.mode=='RGBA' and image.getpixel((0,0))[3]==0
        with Image.open(folder/'walk.gif') as gif:
            for i in range(gif.n_frames):
                gif.seek(i); assert gif.convert('RGBA').getpixel((0,0))[3]==0
        record.update(all_frames_view=True,sprite_sheet_view=True,transparent_png_sheet_gif=True)
        write_json(DATA/'walk-acceptance.json',record); print('All frame/sheet/transparency views passed.',flush=True)
        state['stage']='exit'
    elif state['stage']=='exit' and not window.workers: app.exit(state['code'])


def guard():
    try: tick()
    except Exception as exc:
        print('FAIL',repr(exc),flush=True); window.timer.stop(); state['stage']='exit'; state['code']=1


timer=QTimer(); timer.timeout.connect(guard); timer.start(150)
sys.exit(app.exec())
