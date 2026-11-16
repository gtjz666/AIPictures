"""Native game-kit acceptance. Uses original placeholders, no inference or user scene edits."""
import argparse
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from PIL import Image


def run(godot,project,log,*arguments):
    result=subprocess.run([str(godot),'--headless','--path',str(project),*arguments],capture_output=True,timeout=50)
    text=(result.stdout+result.stderr).decode('utf-8','replace');log.write_text(text,'utf-8')
    if result.returncode or 'ERROR:' in text or 'Assertion failed' in text:raise RuntimeError(text[-6500:])
    print(log.name+': PASS',flush=True)


def setup(project):
    project.mkdir(parents=True,exist_ok=True)
    (project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="AlI Game Kit Proof"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n[global_group]\nali_assets_editor="Editor plugin"\n[editor_plugins]\nenabled=PackedStringArray("res://addons/ali_assets/plugin.cfg")\n','utf-8')
    shutil.copytree('godot_addon/addons/ali_assets',project/'addons/ali_assets',dirs_exist_ok=True)
    fixtures=project/'fixtures';fixtures.mkdir(exist_ok=True)
    (fixtures/'counter.gd').write_text('extends RefCounted\nfunc execute(context: Dictionary) -> Dictionary:\n\tvar game: Node2D = context["game"]\n\tassert(context.has("score") and context.has("delta"))\n\tgame.set_meta("calls", int(game.get_meta("calls", 0)) + 1)\n\tcontext["variables"]["called"] = true\n\treturn {"output": 0}\n','utf-8')
    # Flat colours are deliberate import/assignment fixtures, not artwork quality tests.
    for name,size,colour in [('sky',(96,54),'#cde7e1'),('ground',(48,16),'#386266'),('button',(96,48),'#357b74')]:Image.new('RGB',size,colour).save(fixtures/(name+'.png'))
    with wave.open(str(fixtures/'tone.wav'),'wb') as stream:
        stream.setparams((1,2,22050,0,'NONE','not compressed'))
        stream.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*220*i/22050))) for i in range(22050)))
    shutil.copy2('tools/godot_game_probe.gd',project/'runtime_probe.gd')
    shutil.copy2('tools/godot_game_assets_probe.gd',project/'assets_probe.gd')
    shutil.copy2('tools/godot_game_render_probe.gd',project/'render_probe.gd')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--godot',type=Path,required=True);parser.add_argument('--proof',type=Path,required=True);args=parser.parse_args()
    proof=args.proof.resolve();project=proof/'project'
    if (project/'runner_game.tscn').exists():raise ValueError('Use a new proof directory to preserve previous evidence.')
    setup(project)
    run(args.godot,project,proof/'import.log','--editor','--import')
    probe=project/'addons/ali_probe';probe.mkdir(parents=True,exist_ok=True)
    shutil.copy2('tools/godot_game_editor_probe.gd',probe/'plugin.gd')
    (probe/'plugin.cfg').write_text('[plugin]\nname="Isolated game proof"\ndescription="Acceptance only"\nauthor="AlI"\nversion="1"\nscript="plugin.gd"\n')
    config=project/'project.godot';original=config.read_text('utf-8')
    config.write_text(original.replace('"res://addons/ali_assets/plugin.cfg")','"res://addons/ali_assets/plugin.cfg", "res://addons/ali_probe/plugin.cfg")'),'utf-8')
    try:run(args.godot,project,proof/'editor.log','--editor','--fixed-fps','60','--quit-after','600')
    finally:config.write_text(original,'utf-8')
    assert (project/'editor-proof.json').exists()
    run(args.godot,project,proof/'runtime.log','--script','res://runtime_probe.gd','--fixed-fps','60','--quit-after','900')
    assert (project/'runtime-proof.json').exists()
    run(args.godot,project,proof/'assets.log','--script','res://assets_probe.gd','--fixed-fps','60','--quit-after','600')
    assert (project/'assets-proof.json').exists()
    print('Native game editor and full play/death/restart/audio loop: PASS')


if __name__=='__main__':main()
