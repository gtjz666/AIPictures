import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest

from aipictures.owned_process import gated_module_command
from aipictures.startup_trace import start
from aipictures.storage import write_json


def test_startup_stack_is_durable_and_tracing_stops_at_readiness(tmp_path):
    watch=start(tmp_path,interval=.05,dump_after=.15)
    try:
        time.sleep(.35)
        saved=json.loads((tmp_path/'startup-watch.json').read_text(encoding='utf-8'))
        assert saved['device_queries'] is False
        assert any(Path(frame['file']).name==Path(__file__).name for frame in saved['main_thread_stack'])
        assert saved['native_traceback_timer'] is False
        assert not (tmp_path/'startup-stacks.log').exists()
        write_json(tmp_path/'startup-ready.json',{'ready':True},durable=True)
        watch.thread.join(timeout=2)
        assert not watch.thread.is_alive()
        saved=json.loads((tmp_path/'startup-watch.json').read_text(encoding='utf-8'))
        assert saved['status']=='ready'
        modified=(tmp_path/'startup-watch.json').stat().st_mtime_ns
        time.sleep(.15)
        assert (tmp_path/'startup-watch.json').stat().st_mtime_ns==modified
    finally:
        watch.stop()


def test_bootstrap_observes_only_owned_child_after_gate_and_keeps_arguments(tmp_path):
    (tmp_path/'fake_startup.py').write_text(
        "import json,sys\nfrom pathlib import Path\nPath('args.json').write_text(json.dumps(sys.argv[1:]))\n",
        encoding='utf-8')
    trace=tmp_path/'trace'
    command=gated_module_command([sys.executable,'-u','-m','fake_startup','--seed','123'],startup_trace=trace)
    result=subprocess.run(command,input=b'go\n',cwd=tmp_path,capture_output=True,timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
    assert json.loads((tmp_path/'args.json').read_text())==['--seed','123']
    assert json.loads((trace/'startup-watch.json').read_text(encoding='utf-8'))['status']=='exited_before_ready'
    denied=tmp_path/'denied'
    command=gated_module_command([sys.executable,'-u','-m','fake_startup'],startup_trace=denied)
    result=subprocess.run(command,input=b'',cwd=tmp_path,capture_output=True,timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    assert result.returncode==125
    assert not denied.exists()


def test_startup_diagnostics_has_no_gpu_or_model_dependencies():
    import aipictures.startup_trace as module
    tree=ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
    imports=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom):imports.add(node.module.split('.')[0])
    assert imports <= sys.stdlib_module_names
    assert 'faulthandler' not in imports


@pytest.mark.parametrize('python',list(dict.fromkeys(filter(None,
    (sys.executable,os.environ.get('AIPICTURES_TEST_DEPLOYMENT_PYTHON'))))))
def test_fast_cpu_recording_on_desktop_and_deployment_python(tmp_path,python):
    """The regression must also run on the actual deployment CPython, not just Qt's Python."""
    import aipictures.startup_trace as module
    code=("import runpy,sys,time\nfrom pathlib import Path\n"
          "assert 'torch' not in sys.modules\n"
          f"watch=runpy.run_path({str(Path(module.__file__).resolve())!r})['start']({str(tmp_path)!r},interval=.01,dump_after=.02)\n"
          "end=time.monotonic()+1.0\n"
          "while time.monotonic()<end:\n"
          " p=Path('alpha')/'beta'/'gamma'\n"
          " str(p.parent);p.as_posix();p.parts\n"
          " time.sleep(.001)\n"
          "watch.stop()\nassert 'torch' not in sys.modules\n")
    result=subprocess.run([python,'-I','-u','-c',code],capture_output=True,timeout=15,
        env=dict(os.environ,CUDA_VISIBLE_DEVICES='-1'),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
    saved=json.loads((tmp_path/'startup-watch.json').read_text(encoding='utf-8'))
    assert saved['native_traceback_timer'] is False and saved['device_queries'] is False
    assert not (tmp_path/'startup-stacks.log').exists()
