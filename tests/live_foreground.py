"""Real CPU matte, preserved white RGB, responsive Qt and released inference memory."""
import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer

from aipictures.app import Window,create_application
from aipictures.background import foreground_rgba,release_session,MODEL
from aipictures.storage import DATA,write_json


def resident_bytes():
    value=subprocess.run(['powershell','-NoProfile','-Command',
        f'(Get-Process -Id {os.getpid()}).WorkingSet64'],capture_output=True,text=True,check=True)
    return int(value.stdout.strip())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('image'); parser.add_argument('--opaque',required=True,help='x,y of reviewed white foreground')
    args=parser.parse_args(); source=Path(args.image).resolve()
    x,y=map(int,args.opaque.split(',')); state={'ticks':0,'code':0,'start':time.monotonic()}
    app=create_application([])
    with patch.object(Window,'connect_engine',lambda self:None),patch('aipictures.app.write_json'):
        window=Window(); window.timer.stop(); window.show()
        def action(emit):
            release_session(); before=resident_bytes()
            with Image.open(source) as image:
                raw=image.convert('RGB'); result=foreground_rgba(raw,threading.Event())
            during=resident_bytes(); release_session(); after=resident_bytes()
            assert np.array_equal(np.asarray(result)[:,:,:3],np.asarray(raw))
            assert result.getpixel((x,y))[3]==255
            assert result.getpixel((0,0))[3]==0
            result.save(DATA/'foreground-live-result.png')
            assert after<during*.8,{'before':before,'during':during,'after':after}
            return {'passed':True,'model':MODEL,'source':str(source),'white_foreground_pixel':[x,y],
                'original_rgb_unchanged':True,'transparent_corner':True,
                'resident_bytes_before':before,'resident_bytes_with_session':during,'resident_bytes_after_release':after}
        def event(kind,data):
            if kind=='result':
                assert state['ticks']>50,state
                data['qt_timer_ticks']=state['ticks']; data['elapsed_seconds']=round(time.monotonic()-state['start'],1)
                write_json(DATA/'foreground-live-acceptance.json',data)
                print(data,flush=True); state['done']=True
            elif kind=='error':
                print('FAIL',data,flush=True); state['code']=1; state['done']=True
        def tick():
            state['ticks']+=1
            if state.get('done') and not window.workers: app.exit(state['code'])
        timer=QTimer(); timer.timeout.connect(tick); timer.start(20)
        window.launch(action,event)
        return app.exec()


if __name__=='__main__': sys.exit(main())
