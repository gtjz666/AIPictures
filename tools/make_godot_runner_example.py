"""Create a clean playable project in a new folder. Never overwrite a user's project."""
import argparse
import subprocess
from pathlib import Path
from aipictures.godot_assets import install_addon


def make(project,application,godot):
    project=Path(project).resolve();application=Path(application).resolve()
    if project.exists() and any(project.iterdir()):raise ValueError('请选择新的空文件夹，现有项目保持原样。')
    project.mkdir(parents=True,exist_ok=True)
    (project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="AlIRunnerDemo"\n[display]\nwindow/size/viewport_width=960\nwindow/size/viewport_height=540\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n[editor_plugins]\nenabled=PackedStringArray("res://addons/ali_assets/plugin.cfg")\n','utf-8')
    install_addon(project,application)
    script=Path(__file__).with_name('godot_make_runner_example.gd').resolve()
    run=subprocess.run([str(godot),'--headless','--path',str(project),'--script',str(script)],capture_output=True,timeout=45)
    output=(run.stdout+run.stderr).decode('utf-8','replace')
    if run.returncode or 'ERROR:' in output or 'ALI_RUNNER_EXAMPLE_CREATED' not in output:raise RuntimeError(output)
    (project/'README.md').write_text('打开project.godot后按F5运行。Space开始／跳跃，Esc暂停，R重开。默认图形与声音为原创演示占位。\n\n在右侧AlI素材打开“游戏蓝图／创建小游戏”，选中RunnerGame根节点后“绑定当前游戏”，修改后应用并保存。\n完整教程位于AlI软件docs/GODOT_RUNNER_GUIDE.md。\n','utf-8')
    return project


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--application',type=Path,required=True);parser.add_argument('--godot',type=Path,required=True);args=parser.parse_args()
    print(make(args.project,args.application,args.godot))
