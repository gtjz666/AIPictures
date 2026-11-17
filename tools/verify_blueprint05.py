"""Stage 1 native acceptance, isolated from user scenes and inference backends."""
import argparse
import shutil
from pathlib import Path
from .verify_godot_game import setup, run


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--godot',type=Path,required=True)
    parser.add_argument('--proof',type=Path,required=True)
    args=parser.parse_args()
    proof=args.proof.resolve()
    if proof.exists():raise ValueError('Use a new proof directory.')
    project=proof/'project';setup(project)
    for filename in ('runtime_probe.gd','assets_probe.gd','render_probe.gd'):(project/filename).unlink()
    shutil.copy2('tools/godot_blueprint05_probe.gd',project/'probe.gd')
    run(args.godot,project,proof/'import.log','--editor','--import')
    run(args.godot,project,proof/'runtime.log','--verbose','--script','res://probe.gd','--fixed-fps','60','--quit-after','600')
    assert (project/'blueprint05-proof.json').exists()
    probe=project/'addons/ali_stage1_probe';probe.mkdir(parents=True)
    shutil.copy2('tools/godot_blueprint05_editor_probe.gd',probe/'plugin.gd')
    (probe/'plugin.cfg').write_text('[plugin]\nname="Stage 1 proof"\ndescription="Isolated acceptance"\nauthor="AlI"\nversion="1"\nscript="plugin.gd"\n','utf-8')
    config=project/'project.godot';original=config.read_text('utf-8')
    config.write_text(original.replace('"res://addons/ali_assets/plugin.cfg")','"res://addons/ali_assets/plugin.cfg", "res://addons/ali_stage1_probe/plugin.cfg")'),'utf-8')
    try:run(args.godot,project,proof/'editor.log','--editor','--fixed-fps','60','--quit-after','600')
    finally:config.write_text(original,'utf-8')
    assert (project/'blueprint05-editor-proof.json').exists()
    print('Blueprint 0.5 stage 1 native editor/runtime: PASS')


if __name__=='__main__':main()
