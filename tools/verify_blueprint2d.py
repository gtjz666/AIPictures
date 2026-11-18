"""Isolated native acceptance for the complete 2D framework; no model inference."""
import argparse
import json
import shutil
from pathlib import Path
from .verify_godot_game import setup,run


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--godot',type=Path,required=True);parser.add_argument('--proof',type=Path,required=True);parser.add_argument('--only',default='all');args=parser.parse_args()
    proof=args.proof.resolve()
    if proof.exists():raise ValueError('Use a fresh proof directory.')
    project=proof/'project';setup(project)
    for name in ('runtime_probe.gd','assets_probe.gd','render_probe.gd'):(project/name).unlink()
    role=project/'role_runtime';shutil.copytree('godot_addon/runtime',role)
    for name in ('blueprint_types.gd','blueprint_events.gd','animation_binding.gd','resource_link.gd','blueprint_model.gd'):shutil.copy2(project/'addons/ali_assets'/name,role/name)
    probes=['tasks','world','services','subgraph','framework','ui_role']
    for name in probes:shutil.copy2('tools/godot_blueprint2d_'+name+'_probe.gd',project/(name+'_probe.gd'))
    run(args.godot,project,proof/'import.log','--editor','--import')
    for name in probes:
        if args.only not in ('all',name) and not (args.only=='services' and name=='world'):continue
        run(args.godot,project,proof/(name+'.log'),'--script','res://'+name+'_probe.gd','--fixed-fps','60','--quit-after','1500')
        assert (project/(name+'-proof.json')).exists()
        if name=='framework':
            # Exercise actual initial scene loading, not only add_child after
            # the SceneTree is already idle (which hides the root-busy error).
            shutil.copy2('tools/godot_framework_startup_probe.gd',project/'startup_probe.gd')
            config=project/'project.godot';original=config.read_text('utf-8')
            assert '[autoload]' not in original
            config.write_text(original+'\n[autoload]\nStartupProbe="*res://startup_probe.gd"\n','utf-8')
            try:
                for preset,scene in (('runner','MainMenu'),('runner','Game'),('platformer','Game')):
                    folders=list(project.glob('framework_'+preset+'_*'))
                    assert len(folders)==1
                    name_on_disk=folders[0].name
                    run(args.godot,project,proof/('startup-'+preset+'-'+scene+'.log'),
                        'res://'+name_on_disk+'/'+scene+'.tscn','--fixed-fps','60','--quit-after','900')
                    assert (project/('startup_'+preset+'_'+scene+'.json')).exists()
            finally:config.write_text(original,'utf-8')
    if args.only not in ('all','editor'):return
    from aipictures.godot_assets import export_asset
    fixture=project/'fixtures'
    clips=[fixture/'sky.png',fixture/'sky.png']
    assets={
        'walk':export_asset(project,'drop_walk','animated',{'walk':clips}),
        'jump':export_asset(project,'drop_jump','animated',{'jump':clips[:1]}),
        'role':export_asset(project,'drop_role','two_way',{'walk_right':clips}),
        'image':export_asset(project,'drop_image','image',image=fixture/'sky.png'),
        'voice':export_asset(project,'drop_sound','audio',audio=fixture/'tone.wav'),
    }
    (fixture/'drop.json').write_text(json.dumps({key:value['scene'] for key,value in assets.items()}),'utf-8')
    editor=project/'addons/ali_2d_proof';editor.mkdir()
    shutil.copy2('tools/godot_blueprint2d_editor_probe.gd',editor/'plugin.gd')
    (editor/'plugin.cfg').write_text('[plugin]\nname="2D acceptance"\ndescription="Proof only"\nauthor="AlI"\nversion="1"\nscript="plugin.gd"\n','utf-8')
    config=project/'project.godot';original=config.read_text('utf-8')
    config.write_text(original.replace('"res://addons/ali_assets/plugin.cfg")','"res://addons/ali_assets/plugin.cfg", "res://addons/ali_2d_proof/plugin.cfg")'),'utf-8')
    try:run(args.godot,project,proof/'editor2d.log','--editor','--max-fps','120','--quit-after','1200')
    finally:config.write_text(original,'utf-8')
    assert (project/'editor2d-proof.json').exists(),'Editor acceptance did not complete'
    print('Native 2D framework acceptance: PASS')


if __name__=='__main__':main()
