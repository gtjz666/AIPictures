"""Backup-install addon files and prove all existing project content is preserved."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from aipictures.godot_assets import install_addon


def fingerprint(root):
    result={}
    for folder,dirs,files in os.walk(root):
        relative=Path(folder).relative_to(root)
        dirs[:]=[d for d in dirs if d not in ('.git','.godot','.aipictures') and relative/ d != Path('addons/ali_assets')]
        for filename in files:
            path=Path(folder)/filename
            if path.is_symlink():continue
            result[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--application',type=Path,required=True);parser.add_argument('--proof',type=Path,required=True);parser.add_argument('--project',action='append',type=Path,required=True);parser.add_argument('--godot',type=Path,required=True);parser.add_argument('--validator',type=Path,required=True);args=parser.parse_args()
    proof=args.proof.resolve();proof.mkdir(parents=True,exist_ok=False)
    receipt=[]
    for project in args.project:
        project=project.resolve();before=fingerprint(project)
        backups=set((project/'.aipictures').glob('addon_backup_*'))
        target=install_addon(project,args.application.resolve())
        assert fingerprint(project)==before,'Non-addon project content changed during installation'
        installed=sorted(set((project/'.aipictures').glob('addon_backup_*'))-backups)
        result=subprocess.run([sys.executable,str(args.validator),str(project),'--godot-bin',str(args.godot),'--warnings-as-errors'],capture_output=True,timeout=180)
        output=result.stdout.decode('utf-8','replace');(proof/(project.name+'-validation.json')).write_text(output,'utf-8')
        report=json.loads(output)
        if not report['ok']:raise RuntimeError(str(report['diagnostics'])[:3000])
        after=fingerprint(project)
        assert all(after.get(name)==digest for name,digest in before.items()),'Existing non-addon project file changed during validation'
        additions=set(after)-set(before)
        assert all(name.endswith('.uid') for name in additions),additions
        receipt.append({'project':str(project),'addon':str(target),'backup':[str(p) for p in installed],'protected_files':before,'new_godot_uid_files':sorted(additions),'validation':report['counts']})
        print(project.name+': addon updated; project files preserved; 0 errors/warnings',flush=True)
    (proof/'deployment.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),'utf-8')


if __name__=='__main__':main()
