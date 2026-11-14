"""Remove only four checksum-verified, unadopted AIPictures image candidates."""
import argparse,json,shutil,re,subprocess
from pathlib import Path
from aipictures.engine import ComfyClient,EngineUnavailable
from aipictures.storage import write_json
from aipictures.workflow_library import digest
from tools.prepare_general_models import FILES as QWEN
from tools.install_klein_base_probe import NAME,SIZE,SHA

def specifications():
    return [(Path(folder)/name,size,sha,'Qwen edit validation failed; not in normal auto/Z/FLUX routing')
            for folder,repo,revision,name,size,sha in QWEN]+[(Path('diffusion_models')/NAME,SIZE,SHA,'Base ablation showed no consistent benefit; not adopted')]

def no_local_engines():
    script="ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {$_.Name -match '^python(w)?\\.exe$|^Comfy( Desktop|UI)?\\.exe$'} | Select-Object ProcessId,Name,CommandLine)"
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode:raise ValueError('Process inventory failed; offline deletion refused')
    rows=json.loads(r.stdout)
    if not isinstance(rows,list):raise ValueError('Unrecognized process inventory')
    for row in rows:
        command=row.get('CommandLine')
        if command is None or row['Name'].lower().startswith('comfy') or re.search(r'main\.py|run_module\(.{0,5}main|freevideo_engine|(?:-m\s+main)(?:\s|$)',command,re.I):
            raise ValueError('A local model engine is running or unknown; offline deletion deferred')
    return dict(process_inventory_succeeded=True,local_model_engines=0)

def retire(root,data,report,urls,allow_offline=False):
    root=Path(root).resolve(strict=True);data=Path(data).resolve(strict=True);report=Path(report).resolve()
    if report.exists():raise ValueError('Deletion receipt already exists; inspect it instead of replaying')
    status=json.loads((data/'reference-edit-settings.json').read_text('utf-8'))
    if status.get('validated') is not False:raise ValueError('Qwen edit is no longer explicitly unvalidated')
    clients=[ComfyClient(url) for url in urls]
    if not clients:raise ValueError('Explicit live shared backend is required for queue checks')
    offline=[]
    def idle():
        for client in clients:
            try:q=client.request('/queue',timeout=5)
            except EngineUnavailable:
                if not allow_offline:raise
                offline.append(dict(url=client.url,**no_local_engines()));continue
            if not isinstance(q,dict) or q.get('queue_running') or q.get('queue_pending'):raise ValueError('Shared backend busy or unknown; no task interrupted')
    idle();report.parent.mkdir(parents=True,exist_ok=True)
    result=dict(scope=str(root),reason='User explicitly requested deletion of unused models after comparison',
        retained_active_families=['FLUX.2 Klein distilled','Z-Image','H3 video and shared H3 encoder','matting and depth','local intent','audio'],
        deleted=[],skipped=[],deleted_bytes=0,free_before=shutil.disk_usage(root).free,offline_checks=offline)
    write_json(report,result,durable=True)
    for relative,size,sha,reason in specifications():
        path=root/relative
        if not path.is_file():result['skipped'].append(dict(path=str(path),reason='already absent'));continue
        resolved=path.resolve(strict=True);before=path.stat()
        if path.is_symlink() or resolved!=path.absolute() or not resolved.is_relative_to(root) or before.st_nlink!=1:
            result['skipped'].append(dict(path=str(path),reason='linked, redirected or shared file retained'));continue
        if before.st_size!=size or digest(path)!=sha:
            result['skipped'].append(dict(path=str(path),reason='publisher checksum mismatch; changed file retained'));continue
        idle();after=path.stat()
        if path.resolve(strict=True)!=resolved or (before.st_ino,before.st_mtime_ns,before.st_size)!=(after.st_ino,after.st_mtime_ns,after.st_size):raise ValueError('File changed during verification')
        entry=dict(path=str(resolved),bytes=size,sha256=sha,reason=reason)
        result['pending']=entry;write_json(report,result,durable=True)
        path.unlink()
        if path.exists():raise ValueError('Removal not confirmed')
        result.pop('pending');result['deleted'].append(entry);result['deleted_bytes']+=size
        write_json(report,result,durable=True);print('Removed verified unused candidate: '+relative.as_posix(),flush=True)
    result['free_after']=shutil.disk_usage(root).free
    result['free_delta_observed']=result['free_after']-result['free_before']
    result['free_delta_note']='May include concurrent non-model file activity; deleted_bytes is the exact removed file total.'
    write_json(report,result,durable=True);return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--models',type=Path,required=True);p.add_argument('--data',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--url',action='append',required=True)
    p.add_argument('--allow-offline-if-no-engines',action='store_true');a=p.parse_args()
    r=retire(a.models,a.data,a.report,a.url,a.allow_offline_if_no_engines);print(json.dumps(r,ensure_ascii=False))

if __name__=='__main__':main()
