"""Retire only the two verified standalone prompt-assistant weights and their fragments."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from aipictures.storage import write_json
from aipictures.workflow_library import digest

WEIGHTS={
    'Qwen3VL-8B-Instruct-Q4_K_M.gguf':(5027784800,'67d1659bfe71b89d50b45a4ad1a9e5b997e5bb16ce5da66a6a6167abd569e9e2'),
    'mmproj-Qwen3VL-8B-Instruct-F16.gguf':(1159029824,'ca524100ebf825c9a870db1c580d03879e0da0ab2541697e2458e64891cf9d38')}
FRAGMENTS={
    'Qwen3VL-8B-Instruct-Q4_K_M.gguf.intent-download.part',
    *('Qwen3VL-8B-Instruct-Q4_K_M.gguf.style-download.part.range-'+r for r in
      ('0-1256946199','1256946200-2513892399','2513892400-3770838599','3770838600-5027784799'))}


def idle(root):
    script="ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {$_.Name -match 'llama|python|comfy'} | Select-Object ProcessId,Name,CommandLine)"
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise ValueError('Process inventory failed; nothing removed')
    rows=json.loads(result.stdout)
    if not isinstance(rows,list):raise ValueError('Unknown process inventory')
    for row in rows:
        command=row.get('CommandLine')
        if command is None or 'llama' in row['Name'].lower() or str(root).casefold() in command.casefold():
            raise ValueError('Prompt assistant may be running; nothing removed')
    return dict(process_inventory_succeeded=True,assistant_processes=0)


def candidates(root):
    absolute=Path(root).absolute();root=absolute.resolve(strict=True)
    if root!=absolute or root.is_symlink():raise ValueError('Redirected assistant root refused')
    models=root/'models'
    if models.resolve(strict=True)!=models or models.is_symlink():raise ValueError('Redirected models directory refused')
    receipt=json.loads((root/'installation.json').read_text('utf-8'))
    installed={Path(row['path']).name:row for row in receipt['files']}
    planned=[]
    for name in sorted(set(WEIGHTS)|FRAGMENTS):
        path=models/name
        if not path.exists():continue
        stat=path.stat()
        if path.resolve(strict=True)!=path or path.is_symlink() or stat.st_nlink!=1 or not path.is_file():raise ValueError('Linked/shared assistant file refused')
        if name in WEIGHTS:
            size,sha=WEIGHTS[name];row=installed.get(name,{})
            if (row.get('bytes'),row.get('sha256'))!=(size,sha) or Path(row['path']).resolve()!=path:raise ValueError('Installation receipt does not match allowlist')
            if stat.st_size!=size or digest(path)!=sha:raise ValueError('Assistant weight checksum mismatch')
        else:sha=digest(path)
        after=path.stat()
        if (after.st_size,after.st_mtime_ns,after.st_ctime_ns,after.st_ino,after.st_nlink)!=(stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,stat.st_ino,stat.st_nlink):
            raise ValueError('Assistant file changed during verification')
        planned.append(dict(path=str(path),bytes=stat.st_size,sha256=sha,mtime_ns=stat.st_mtime_ns))
    return root,planned


def retire(root,data,report,apply=False):
    report=Path(report).resolve();data=Path(data).resolve(strict=True)
    if report.exists():raise ValueError('Receipt exists; inspect it instead of repeating deletion')
    idle(Path(root).resolve(strict=True));root,planned=candidates(root)
    # No active model setting may share one of the retired weights. The retired
    # standalone assistant setting is archived below; native encoders stay intact.
    paths={row['path'].casefold().replace('\\','/') for row in planned}
    for p in data.glob('*settings.json'):
        if p.name=='local-intent-settings.json':continue
        value=p.read_text('utf-8').casefold().replace('\\\\','/')
        if any(path in value for path in paths):raise ValueError('Weight is referenced by another active engine')
    status=dict(scope=str(root),policy='manual_verbatim_v1',status='planned',files=planned,deleted=[],deleted_bytes=0,
        free_before=shutil.disk_usage(root).free,process_check=idle(root),retained='H3/Image/audio native text encoders, runtime executables, install receipt')
    write_json(report,status,durable=True)
    if not apply:return status
    setting=data/'local-intent-settings.json'
    if setting.exists():
        config=json.loads(setting.read_text('utf-8'));write_json(report.with_name(report.stem+'-settings-backup.json'),config,durable=True)
        config.update(validated=False,retired=True,retirement_reason='Manual prompts; no prompt assistant or translation in production')
        write_json(setting,config,durable=True)
    for row in planned:
        idle(root);path=Path(row['path']);stat=path.stat()
        if stat.st_size!=row['bytes'] or stat.st_mtime_ns!=row['mtime_ns'] or path.is_symlink() or path.resolve()!=path or stat.st_nlink!=1:
            raise ValueError('Verified file changed; deletion stopped')
        path.unlink();status['deleted'].append(row);status['deleted_bytes']+=row['bytes'];write_json(report,status,durable=True)
    status.update(status='retired',free_after=shutil.disk_usage(root).free)
    write_json(report,status,durable=True);return status


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--data',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    value=retire(a.root,a.data,a.report,a.apply);print(json.dumps(dict(status=value['status'],deleted_bytes=value['deleted_bytes'],candidates=len(value['files']))))


if __name__=='__main__':main()
