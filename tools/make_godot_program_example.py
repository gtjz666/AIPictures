"""Create a separate, clean native blueprint lab; never overwrite an existing project."""
import argparse
import subprocess
from pathlib import Path
from aipictures.godot_assets import install_addon


def make(project,application,godot):
    project=Path(project).resolve()
    if project.exists() and any(project.iterdir()):raise ValueError('请选择新的空文件夹；原项目保留。')
    project.mkdir(parents=True,exist_ok=True)
    (project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="AlIBlueprintDemo"\n[display]\nwindow/size/viewport_width=960\nwindow/size/viewport_height=540\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n[global_group]\nali_assets_editor="Editor plugin"\n[editor_plugins]\nenabled=PackedStringArray("res://addons/ali_assets/plugin.cfg")\n','utf-8')
    install_addon(project,application)
    result=subprocess.run([str(godot),'--headless','--path',str(project),'--script',str(Path(__file__).with_name('godot_program_example.gd').resolve())],capture_output=True,timeout=30)
    text=(result.stdout+result.stderr).decode('utf-8','replace')
    if result.returncode or 'ERROR:' in text or 'ALI_PROGRAM_EXAMPLE_OK' not in text:raise RuntimeError(text)
    (project/'README.md').write_text('打开project.godot，F5运行。Space开始，J受伤、K恢复、F切换attack后回idle；Esc暂停、R重开。生命耗尽出现结束菜单。\n\n右侧AlI素材→游戏蓝图，选中SceneGame，绑定当前游戏，即可查看／修改预设组合。这个工程验证基础模块，没有AI生成美术或完整战斗。\n完整说明见AlI软件docs/GODOT_BLUEPRINT_TECHNICAL.md及蓝图模块手册。\n','utf-8')
    return project


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--application',type=Path,required=True);parser.add_argument('--godot',type=Path,required=True);args=parser.parse_args()
    print(make(args.project,args.application,args.godot))
