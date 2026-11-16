"""Isolated native acceptance for typed data, flow, FSM, scenes and compiled subgraphs."""
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
    if proof.exists():raise ValueError('Use a new proof directory to preserve evidence.')
    project=proof/'project';setup(project)
    for filename in ('runtime_probe.gd','assets_probe.gd','render_probe.gd'):(project/filename).unlink()
    (project/'fixtures/entity.gd').write_text('extends Node2D\nsignal activated(value: int, extra: String)\nfunc trigger(value: int) -> void:\n\tactivated.emit(value, "extra")\n','utf-8')
    shutil.copy2('tools/godot_program_probe.gd',project/'program_probe.gd')
    run(args.godot,project,proof/'import.log','--editor','--import')
    run(args.godot,project,proof/'program.log','--script','res://program_probe.gd','--fixed-fps','60','--quit-after','600')
    assert (project/'program-proof.json').exists()
    probe=project/'addons/ali_program_probe';probe.mkdir(parents=True)
    shutil.copy2('tools/godot_program_editor_probe.gd',probe/'plugin.gd')
    (probe/'plugin.cfg').write_text('[plugin]\nname="Isolated program proof"\ndescription="Acceptance only"\nauthor="AlI"\nversion="1"\nscript="plugin.gd"\n','utf-8')
    config=project/'project.godot';original=config.read_text('utf-8')
    config.write_text(original.replace('"res://addons/ali_assets/plugin.cfg")','"res://addons/ali_assets/plugin.cfg", "res://addons/ali_program_probe/plugin.cfg")'),'utf-8')
    try:run(args.godot,project,proof/'editor.log','--editor','--fixed-fps','60','--quit-after','600')
    finally:config.write_text(original,'utf-8')
    assert (project/'program-editor-proof.json').exists()
    print((project/'program-proof.json').read_text('utf-8'))


if __name__=='__main__':main()
