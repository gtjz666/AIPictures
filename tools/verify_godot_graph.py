"""Isolated native Godot graph/editor/runtime proof. No AI or user scene edits."""
import argparse
import json
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from PIL import Image
from aipictures.godot_assets import export_asset, ADDON


def setup(project):
    project.mkdir(parents=True, exist_ok=True)
    (project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="AlI Graph Acceptance"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n[global_group]\nali_assets_editor="Editor plugin only"\n[editor_plugins]\nenabled=PackedStringArray("res://addons/ali_assets/plugin.cfg")\n','utf-8')
    shutil.copytree(ADDON/'addons/ali_assets',project/'addons/ali_assets',dirs_exist_ok=True)
    sources=project/'sources';sources.mkdir(exist_ok=True)
    (sources/'custom.gd').write_text('extends RefCounted\nfunc execute(context: Dictionary) -> Dictionary:\n\tvar actor: CharacterBody2D = context["actor"]\n\tactor.set_meta("custom_calls", int(actor.get_meta("custom_calls", 0)) + 1)\n\tcontext["variables"]["custom_ran"] = true\n\treturn {"output": 0}\n','utf-8')
    frames=[]
    for n in range(16):
        p=sources/f'{n}.png';Image.new('RGBA',(16,24),(n*15,100,170,255)).save(p);frames.append(p)
    sound=sources/'tone.wav'
    with wave.open(str(sound),'wb') as w:
        w.setparams((1,2,22050,0,'NONE','not compressed'))
        w.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*440*i/22050))) for i in range(2205)))
    common={name+'_right':frames[:4] for name in ['idle','walk','run','jump','attack','hurt','death','dash','roll','block','cast','interact','climb','fall','land']}
    records=[]
    for preset in ['two_way','four_way','platformer']:
        clips=dict(common)
        if preset=='four_way':clips.update({'walk_'+d:frames[i*4:(i+1)*4] for i,d in enumerate(['left','right','up','down'])})
        records.append(dict(preset=preset,**export_asset(project,preset,preset,clips,audio=sound,fps=12)))
    (project/'probe-inputs.json').write_text(json.dumps(records),'utf-8')
    for name in ['godot_graph_runtime_probe.gd','godot_editor_probe.gd']:shutil.copy2(Path('tools')/name,project/name)


def run(godot,project,log,*args):
    result=subprocess.run([str(godot),'--headless','--path',str(project),*args],capture_output=True,timeout=55)
    output=(result.stdout+result.stderr).decode('utf-8','replace');log.write_text(output,'utf-8')
    if result.returncode or any(s in output for s in ['SCRIPT ERROR:','ERROR:','Assertion failed']):raise RuntimeError(f'{log.name}: exit {result.returncode}\n{output[-7000:]}')
    print(log.name+': PASS',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--godot',type=Path,required=True);parser.add_argument('--proof',type=Path,required=True);args=parser.parse_args()
    proof=args.proof.resolve();proof.mkdir(parents=True,exist_ok=True);project=proof/'project';setup(project)
    run(args.godot,project,proof/'import.log','--editor','--import')
    config=project/'project.godot';original=config.read_text('utf-8')
    probe=project/'addons/ali_probe';probe.mkdir(parents=True,exist_ok=True)
    shutil.copy2('tools/godot_editor_probe.gd',probe/'plugin.gd')
    (probe/'plugin.cfg').write_text('[plugin]\nname="Graph acceptance only"\ndescription="Isolated proof"\nauthor="AlI"\nversion="1"\nscript="plugin.gd"\n')
    config.write_text(original.replace('"res://addons/ali_assets/plugin.cfg")','"res://addons/ali_assets/plugin.cfg", "res://addons/ali_probe/plugin.cfg")'),'utf-8')
    try:run(args.godot,project,proof/'editor.log','--editor','--fixed-fps','60','--quit-after','300')
    finally:config.write_text(original,'utf-8')
    assert (project/'blueprint-proof.json').exists(),'Editor proof did not complete'
    run(args.godot,project,proof/'runtime.log','--script','res://godot_graph_runtime_probe.gd','--fixed-fps','60','--quit-after','600')
    assert (project/'runtime-proof.json').exists(),'Runtime proof did not complete'
    print('Native graph editor, persistence, validation and input/animation/audio runtime: PASS')


if __name__=='__main__':main()
