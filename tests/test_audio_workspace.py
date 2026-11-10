import json
import os
import subprocess
import sys
import threading
from unittest.mock import patch
import pytest
from aipictures.audio_generation import generate
from aipictures.engine import Cancelled
from aipictures.result_cache import ResultCache


def test_three_categories_native_qt_contract():
    run=subprocess.run([sys.executable,'-m','tools.verify_three_categories'],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=60)
    assert run.returncode==0,(run.stdout+run.stderr).decode('utf-8','replace')


def test_audio_cancel_never_loads_a_model(tmp_path):
    cancel=threading.Event();cancel.set()
    with patch('aipictures.audio_generation.subprocess.Popen') as start,pytest.raises(Cancelled):
        generate(tmp_path,dict(audio_settings={}),cancel,lambda *_:None)
    start.assert_not_called()
    assert json.loads((tmp_path/'audio.json').read_text('utf-8'))['status']=='cancelled'


@pytest.mark.parametrize('seconds',[0,9,181,float('nan')])
def test_invalid_audio_request_fails_before_backend(tmp_path,seconds):
    with patch('aipictures.audio_generation.subprocess.Popen') as start,pytest.raises(ValueError):
        generate(tmp_path,dict(audio_settings={},seconds=seconds,prompt='Piano music',seed=1),threading.Event(),lambda *_:None)
    start.assert_not_called()


def test_audio_exports_are_kept_outside_managed_cache(tmp_path):
    cache=ResultCache(tmp_path)
    with pytest.raises(ValueError):cache.validate_export(tmp_path/'audio/job/output.wav')
    assert cache.validate_export(tmp_path/'saved/music.wav')==tmp_path/'saved/music.wav'
