import os
from pathlib import Path
import subprocess
import sys

from tests.test_api_backend import api_server


def test_actual_qt_cloud_controls_and_results(api_server):
    result = subprocess.run([sys.executable,'-m','tests.live_api_controls',api_server['url']],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),
        capture_output=True,timeout=40)
    assert result.returncode==0,result.stdout.decode('utf-8','replace')+result.stderr.decode('utf-8','replace')
    assert 'PASS' in result.stdout.decode('utf-8','replace')
    assert any(row[1].endswith('/images/generations') for row in api_server['requests'])
