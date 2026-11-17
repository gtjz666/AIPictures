"""Render native UI in a separate, hidden proof process; never touch live apps."""
import argparse
import shutil
import subprocess
from pathlib import Path
from .verify_godot_game import setup,run


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--godot',type=Path,required=True);parser.add_argument('--proof',type=Path,required=True);args=parser.parse_args()
    proof=args.proof.resolve()
    if proof.exists():raise ValueError('Use a fresh proof directory')
    project=proof/'project';setup(project)
    for name in ('runtime_probe.gd','assets_probe.gd','render_probe.gd'):(project/name).unlink()
    shutil.copy2('tools/godot_blueprint2d_menu_visual.gd',project/'visual_probe.gd')
    run(args.godot,project,proof/'import.log','--editor','--import')
    options={}
    if hasattr(subprocess,'STARTUPINFO'):
        info=subprocess.STARTUPINFO();info.dwFlags|=subprocess.STARTF_USESHOWWINDOW;info.wShowWindow=0;options['startupinfo']=info
    result=subprocess.run([str(args.godot),'--path',str(project),'--script','res://visual_probe.gd','--quit-after','300'],capture_output=True,timeout=50,**options)
    text=(result.stdout+result.stderr).decode('utf-8','replace');(proof/'render.log').write_text(text,'utf-8')
    if result.returncode or 'ERROR:' in text:raise RuntimeError(text[-6500:])
    probe=project/'addons/ali_visual_proof';probe.mkdir()
    shutil.copy2('tools/godot_blueprint2d_visual_probe.gd',probe/'plugin.gd')
    (probe/'plugin.cfg').write_text('[plugin]\nname="Visual proof"\ndescription="Proof"\nauthor="AlI"\nversion="1"\nscript="plugin.gd"\n','utf-8')
    config=project/'project.godot';original=config.read_text('utf-8');config.write_text(original.replace('"res://addons/ali_assets/plugin.cfg")','"res://addons/ali_assets/plugin.cfg", "res://addons/ali_visual_proof/plugin.cfg")'),'utf-8')
    try:
        result=subprocess.run([str(args.godot),'--path',str(project),'--editor','--quit-after','300'],capture_output=True,timeout=50,**options)
        text=(result.stdout+result.stderr).decode('utf-8','replace');(proof/'editor-render.log').write_text(text,'utf-8')
        if result.returncode or 'ERROR:' in text:raise RuntimeError(text[-6500:])
    finally:config.write_text(original,'utf-8')
    for name in ('editor','menu','settings'):assert (project/f'blueprint-2d-{name}.png').exists()
    print('Native visual renders: PASS')


if __name__=='__main__':main()
