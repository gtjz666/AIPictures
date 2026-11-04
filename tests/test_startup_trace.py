import ast
import json
from pathlib import Path
import subprocess
import sys
import time

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
        assert Path(__file__).name in (tmp_path/'startup-stacks.log').read_text(encoding='utf-8')
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
