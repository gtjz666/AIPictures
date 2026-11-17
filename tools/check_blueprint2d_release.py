"""Build a clean production-only project, extract schema, and validate all scenes."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from .verify_godot_game import run
from .build_blueprint_catalog import build


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--godot',type=Path,required=True);parser.add_argument('--proof',type=Path,required=True);parser.add_argument('--validator',type=Path,required=True);args=parser.parse_args()
    proof=args.proof.resolve()
    if proof.exists():raise ValueError('Use a fresh proof directory')
    project=proof/'project';project.mkdir(parents=True)
    shutil.copytree('godot_addon/addons/ali_assets',project/'addons/ali_assets')
    (project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="AlI 2D Release Check"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n[editor_plugins]\nenabled=PackedStringArray("res://addons/ali_assets/plugin.cfg")\n','utf-8')
    (project/'build.gd').write_text('extends SceneTree\nconst Builder: GDScript = preload("res://addons/ali_assets/framework_builder.gd")\nfunc _initialize() -> void:\n\tfor preset: String in Builder.PRESETS:\n\t\tvar result: Dictionary = Builder.create("res://cases/"+preset,preset)\n\t\tassert(not result.has("error"),str(result))\n\tquit(0)\n','utf-8')
    run(args.godot,project,proof/'import.log','--editor','--import')
    run(args.godot,project,proof/'build.log','--script','res://build.gd')
    shutil.copy2('tools/export_blueprint_catalog.gd',project/'schema.gd')
    result=subprocess.run([str(args.godot),'--headless','--path',str(project),'--script','res://schema.gd'],capture_output=True,timeout=40)
    output=(result.stdout+result.stderr).decode('utf-8','replace');(proof/'schema.log').write_text(output,'utf-8')
    if result.returncode or 'ERROR:' in output:raise RuntimeError(output[-6000:])
    schema=json.loads(next(line.split('=',1)[1] for line in output.splitlines() if line.startswith('BLUEPRINT_CATALOG_JSON=')))
    assert len(schema['game_modules'])==71 and len(schema['character_types'])==13
    (proof/'schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),'utf-8')
    Path('docs/GODOT_BLUEPRINT_CATALOG.md').write_text(build(schema),'utf-8')
    command=[sys.executable,str(args.validator),str(project),'--godot-bin',str(args.godot),'--warnings-as-errors']
    result=subprocess.run(command,capture_output=True,timeout=180)
    output=result.stdout.decode('utf-8','replace');(proof/'validation.json').write_text(output,'utf-8')
    report=json.loads(output)
    print(json.dumps({'ok':report['ok'],'counts':report['counts'],'checked':report['static']['counts']},ensure_ascii=False),flush=True)
    if not report['ok']:
        print([(Path(d.get('file','')).name,d.get('line'),d.get('message')) for d in report['diagnostics']][:30]);raise RuntimeError('Release validation failed')


if __name__=='__main__':main()
