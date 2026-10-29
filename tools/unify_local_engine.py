"""One-time, explicit consolidation of this installation's idle duplicate server."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from aipictures.backend_connection import local_processes,desktop_urls,reachable
from aipictures.engine import ComfyClient
from aipictures.engine_service import release_idle_models
from aipictures.storage import DATA,write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--data',type=Path,default=DATA)
    args=parser.parse_args()
    choices=[url for url in desktop_urls(local_processes()) if reachable(url)]
    if len(choices)!=1: raise RuntimeError('需要一套已就绪且可明确识别的 Comfy Desktop 服务。')
    target=choices[0]; client=ComfyClient(target)
    # Check both queues before touching the old standalone server.
    for url in (target,'http://127.0.0.1:8188'):
        if not reachable(url): continue
        queue=ComfyClient(url).request('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise RuntimeError('仍有任务，保留所有服务：'+url)
    report={'target':target,'mode':'apply' if args.apply else 'preview','stopped':[]}
    if target=='http://127.0.0.1:8188':
        report['note']='Desktop 已使用 8188，无需关闭服务。'
    elif reachable('http://127.0.0.1:8188'):
        # Static script; the only interpolated value is a validated numeric PID.
        query="Get-NetTCPConnection -State Listen -LocalPort 8188 | Select-Object -ExpandProperty OwningProcess -Unique"
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',query],capture_output=True,text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,timeout=20,check=True)
        listeners=[int(value) for value in result.stdout.split()]
        if len(listeners)!=1: raise RuntimeError('8188 监听进程不唯一，保留。')
        pid=listeners[0]; row=next((row for row in local_processes() if row['ProcessId']==pid),None)
        command=(row or {}).get('CommandLine') or ''
        expected=r'D:\Local Comfy\ComfyUI\.venv\Scripts\python.exe'
        if not row or row['Name'].lower()!='python.exe' or expected.lower() not in command.lower() or not (
            re.search(r'--port\s+8188(?:\s|$)',command) and '--cache-ram 4' in command and '--listen 127.0.0.1' in command):
            raise RuntimeError('此进程不是本软件的现有本地启动配置，保留。')
        report['duplicate_pid']=pid
        if args.apply:
            old=ComfyClient('http://127.0.0.1:8188')
            if not release_idle_models(old).get('released'): raise RuntimeError('旧服务仍忙，保留。')
            queue=old.request('/queue')
            if queue.get('queue_running') or queue.get('queue_pending'): raise RuntimeError('出现新任务，保留。')
            # Revalidate identity in the same PowerShell command before terminating.
            script=(f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; "
                "if ($p.Name -ne 'python.exe' -or $p.CommandLine -notlike '*--port 8188 --cache-ram 4*') { throw 'Process changed' }; "
                f"Stop-Process -Id {pid} -ErrorAction Stop")
            subprocess.run(['powershell.exe','-NoProfile','-Command',script],check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
            report['stopped'].append(pid)
    if args.apply:
        path=args.data/'settings.json'; settings=json.loads(path.read_text('utf-8')) if path.is_file() else {}
        settings['url']=target; write_json(path,settings)
        write_json(args.data/'backend-consolidation.json',report)
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__': main()
