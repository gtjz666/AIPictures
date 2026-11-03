import os
from pathlib import Path
import subprocess
import sys
import tempfile


def test_actual_canvas_import_and_dock_layout():
    with tempfile.TemporaryFile() as log:
        result=subprocess.run([sys.executable,'-m','tools.verify_dock_workspace'],cwd=Path(__file__).resolve().parents[1],
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),stdout=log,stderr=log,timeout=40)
        log.seek(0)
        assert result.returncode==0,log.read().decode('utf-8','replace')
