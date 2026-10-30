import os
from pathlib import Path
import subprocess
import sys


def test_process_exits_while_model_worker_is_blocked():
    environment=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8')
    result=subprocess.run([sys.executable,'-m','tests.live_cancel_close','--child'],
        cwd=Path(__file__).resolve().parents[1],env=environment,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr.decode('utf-8','replace')
