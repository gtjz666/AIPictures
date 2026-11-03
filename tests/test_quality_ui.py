import os
from pathlib import Path
import subprocess
import tempfile
import sys


def test_actual_quality_controls():
    # Windows launcher descendants may retain inherited PIPE handles after exit.
    # A real log keeps the same assertions/timeout without waiting on pipe EOF.
    with tempfile.TemporaryFile() as log:
        result=subprocess.run([sys.executable,'-m','tests.live_quality_controls'],cwd=Path(__file__).resolve().parents[1],
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),stdout=log,stderr=log,timeout=30)
        log.seek(0)
        assert result.returncode==0,log.read().decode('utf-8','replace')
