import os
from pathlib import Path
import subprocess
import sys


def test_actual_quality_controls():
    result=subprocess.run([sys.executable,'-m','tests.live_quality_controls'],cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout.decode('utf-8','replace')+result.stderr.decode('utf-8','replace')
