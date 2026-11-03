import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest
from aipictures.animation_timeline import validate_rows


def test_invalid_timeline_never_enters_generation():
    with pytest.raises(ValueError):validate_rows([dict(start=float('nan'),end=1,description='动作')],4)
    with pytest.raises(ValueError):validate_rows([dict(start=0,end=5,description='动作')],4)
    with pytest.raises(ValueError):validate_rows([dict(start=0,end=3,description='动作'),dict(start=2,end=4,description='动作')],4)


def test_actual_qt_editor_and_motion_only_drop():
    with tempfile.TemporaryFile() as log:
        result=subprocess.run([sys.executable,'-m','tools.verify_animation_editor'],cwd=Path(__file__).resolve().parents[1],
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),stdout=log,stderr=log,timeout=40)
        log.seek(0);assert result.returncode==0,log.read().decode('utf-8','replace')
