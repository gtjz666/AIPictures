import json
import threading
import subprocess,os,sys
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from aipictures.godot_assets import export_asset,project_root
from aipictures.workflow_library import digest
from aipictures.engine import Cancelled


def test_actual_qt_godot_export_and_launch_controls():
    result=subprocess.run([sys.executable,'-m','tools.verify_godot_ui'],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),capture_output=True,timeout=60)
    assert result.returncode==0,(result.stdout+result.stderr).decode('utf-8','replace')


@pytest.fixture
def assets(tmp_path):
    project=tmp_path/'project';project.mkdir();(project/'project.godot').write_text('config_version=5\n')
    frames=[]
    for n in range(8):
        p=tmp_path/f'{n}.png';Image.new('RGBA',(16,24),(20*n,70,90,0 if n==0 else 255)).save(p);frames.append(p)
    return project,frames


def test_export_preserves_alpha_source_and_publishes_self_contained_scene(assets):
    project,frames=assets;before={p:digest(p) for p in frames}
    result=export_asset(project,'hero','two_way',{'walk_right':frames},output_height=48)
    root=Path(result['folder']);record=json.loads((root/'asset.json').read_text('utf-8'))
    assert record['preset']=='two_way' and (root/'player.gd').exists()
    with Image.open(root/'frame_0000.png') as im:assert im.size==(32,48) and im.getextrema()[-1]==(0,0)
    assert all(digest(p)==sha for p,sha in before.items())
    assert result['resource'].startswith('res://generated/ali_assets/')
    assert str(frames[0]) not in Path(result['scene']).read_text('utf-8')


def test_four_way_requires_distinct_complete_direction_clips(assets):
    project,frames=assets
    with pytest.raises(ValueError,match='完整'):export_asset(project,'hero','four_way',{'walk_right':frames})
    with pytest.raises(ValueError,match='不同的帧'):export_asset(project,'hero','four_way',{k:frames for k in ('walk_down','walk_up','walk_left','walk_right')})
    assert not (project/'generated').exists()


def test_platform_actions_are_named_and_one_shots_do_not_loop(assets):
    project,frames=assets
    clips={'walk_right':frames,'run_right':frames,'jump_right':frames[:2],'attack_right':frames[2:4],'hurt_right':frames[4:6],'death_right':frames[6:]}
    result=export_asset(project,'hero','platformer',clips)
    scene=Path(result['scene']).read_text('utf-8')
    assert 'platformer = true' in scene and '"name":&"run_right","speed":8.0,"loop":true' in scene
    assert '"name":&"attack_right","speed":8.0,"loop":false' in scene
    script=(Path(result['folder'])/'player.gd').read_text('utf-8')
    assert '@export var key_attack' in script and 'signal attack_requested' in script


def test_export_cannot_follow_project_redirect(tmp_path,assets):
    project,frames=assets;outside=tmp_path/'outside';outside.mkdir()
    # Hard redirects are validated in production; resolve() test is portable even
    # when Windows disallows creating directory symlinks in the test account.
    with patch.object(Path,'resolve',autospec=True,side_effect=lambda p,**_:outside if p==project/'generated'/'ali_assets' else p.absolute()):
        with pytest.raises(ValueError,match='项目之外'):export_asset(project,'hero','animated',{'default':frames})
    assert not list(outside.iterdir())


def test_cancel_before_export_never_writes_a_component(assets):
    project,frames=assets;cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):export_asset(project,'hero','animated',{'default':frames},cancel=cancel)
    assert not (project/'generated').exists()


def test_project_and_source_validation_happens_before_publish(assets,tmp_path):
    project,frames=assets
    with pytest.raises(ValueError,match='project.godot'):project_root(tmp_path)
    other=tmp_path/'other.png';Image.new('RGBA',(32,32)).save(other)
    with pytest.raises(ValueError,match='尺寸'):export_asset(project,'hero','animated',{'default':[frames[0],other]})
    assert not (project/'generated').exists()
