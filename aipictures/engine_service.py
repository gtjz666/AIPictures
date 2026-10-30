"""Start the existing local installation, without replacing its environment or models."""
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from .engine import ComfyClient


def release_idle_models(client):
    """Yield inference caches before CPU segmentation, respecting other clients' jobs."""
    try:
        queue=client.request('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            return {'released':False,'reason':'engine_busy'}
        client.request('/free',{'unload_models':True,'free_memory':True})
        return {'released':True}
    except Exception as exc:
        return {'released':False,'reason':str(exc)}


def start_local_engine(url, emit, timeout=120):
    from .backend_connection import shared_backend_url,desktop_urls,local_processes
    url=shared_backend_url(url)
    parsed=urlparse(url)
    client=ComfyClient(url)
    try:
        client.request('/system_stats')
        return client.url
    except Exception: pass
    if parsed.hostname not in ('127.0.0.1','localhost') or (parsed.port or 80) not in (8188,8189):
        raise ValueError('一键启动使用本机 8188 端口，或复用已打开的 ComfyUI。其他地址请手动启动后连接。')
    existing_desktop=desktop_urls(local_processes())
    url=existing_desktop[0] if existing_desktop else 'http://127.0.0.1:8188'
    client=ComfyClient(url)
    emit('starting', 'ComfyUI Desktop 正在准备，等待现有后端就绪…' if existing_desktop else '正在启动现有 ComfyUI，首次准备可能需要一两分钟…')
    script=Path(__file__).resolve().parent.parent/'start-comfy.ps1'
    log=script.parent/'data'/'logs'/'engine-launch.log'; log.parent.mkdir(parents=True,exist_ok=True)
    # Detached descendants can inherit PIPE handles on Windows, keeping communicate()
    # blocked even after PowerShell exits. A real log file has no EOF wait dependency.
    result=None
    if not existing_desktop:
        with log.open('ab') as output:
            try:
                result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],
                    stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=20)
            except subprocess.TimeoutExpired:
                result=None  # A spawned engine may still be starting; never launch it twice.
    if result is not None and result.returncode:
        raise RuntimeError('本地引擎启动失败，请查看 data/logs/engine-launch.log。')
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            url=shared_backend_url(url)
            client=ComfyClient(url)
            client.request('/system_stats')
            return client.url
        except Exception:
            time.sleep(2)
    raise TimeoutError('ComfyUI 尚未就绪，请稍后点“连接 / 刷新模型”；启动日志位于 data/logs。')
