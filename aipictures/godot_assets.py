"""Portable Godot 4 assets; explicit presets, no prompt interpretation or code generation."""
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4
from PIL import Image
from .storage import write_json
from .workflow_library import digest

ADDON=Path(__file__).resolve().parents[1]/'godot_addon'
PRESETS={'animated','two_way','four_way','platformer','image','audio'}
ACTIONS=(('待机','idle'),('行走','walk'),('奔跑','run'),('跳跃','jump'),('攻击','attack'),('受击','hurt'),('死亡','death'),
    ('冲刺','dash'),('翻滚','roll'),('防御','block'),('施法','cast'),('交互','interact'),('攀爬','climb'),('下落','fall'),('落地','land'))


def project_root(path):
    root=Path(path).resolve(strict=True)
    if not (root/'project.godot').is_file():raise ValueError('请选择包含project.godot的Godot项目文件夹。')
    return root


def install_addon(project,application):
    root=project_root(project);application=Path(application).resolve(strict=True)
    python=application/'.venv/Scripts/pythonw.exe'
    if not python.is_file():python=application/'.venv/Scripts/python.exe'
    if not python.is_file() or not (application/'aipictures/app.py').is_file():raise ValueError('软件目录或Python环境不完整。')
    target=root/'addons'/'ali_assets'
    if not target.resolve().is_relative_to(root):raise ValueError('插件目录指向项目之外，未覆盖。')
    source=ADDON/'addons'/'ali_assets'
    # Existing installations may contain user edits; keep a complete file backup.
    backup=root/'.aipictures'/('addon_backup_'+uuid4().hex[:8])
    # Publish preloaded dependencies before the entry script (an open editor may reload it).
    for p in sorted(source.iterdir(),key=lambda p:(p.name=='plugin.gd',p.name)):
        if not p.is_file() or p.suffix not in ('.gd','.cfg'):continue
        out=target/p.name
        if not out.resolve().is_relative_to(root) or out.is_symlink():raise ValueError('插件文件路径被重定向。')
        if out.exists():backup.mkdir(parents=True,exist_ok=True);shutil.copy2(out,backup/out.name)
        out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
    config=target/'application.json'
    if not config.resolve().is_relative_to(root) or config.is_symlink():raise ValueError('插件配置路径被重定向。')
    if config.exists():backup.mkdir(parents=True,exist_ok=True);shutil.copy2(config,backup/config.name)
    write_json(config,dict(root=str(application),python=str(python)))
    return target


def export_asset(project,name,preset,animations=None,*,image=None,audio=None,fps=8,output_height=0,loop=True,cancel=None):
    from .engine import Cancelled
    def check():
        if cancel is not None and cancel.is_set():raise Cancelled('Godot组件导出已取消，原素材保留。')
    check()
    root=project_root(project)
    if preset not in PRESETS:raise ValueError('请选择有效的Godot组件预设。')
    if not isinstance(name,str) or not name.strip() or len(name)>60:raise ValueError('素材名称须为1–60字。')
    if not 1<=fps<=60 or not 0<=output_height<=2048:raise ValueError('帧率或像素高度无效。')
    animations=animations or {}
    required={'walk_right'} if preset in ('two_way','platformer') else {'walk_up','walk_down','walk_left','walk_right'} if preset=='four_way' else set()
    allowed=re.compile(r'^(?:default|'+ '|'.join(key for _,key in ACTIONS)+r')(?:_(?:up|down|left|right))?$')
    if not required.issubset(animations) or (preset=='animated' and not animations) or any(not allowed.fullmatch(n) or not frames or len(frames)>10000 for n,frames in animations.items()):raise ValueError('动画预设需要完整的对应方向帧；动作可选待机、行走、奔跑、跳跃、攻击、受击和死亡。')
    if preset=='four_way':
        sets=[set(map(lambda p:str(Path(p).resolve()),animations[k])) for k in required]
        if any(a&b for i,a in enumerate(sets) for b in sets[i+1:]):raise ValueError('四个方向需要分别指定不同的帧范围。')
    sources=list(dict.fromkeys(Path(p).resolve(strict=True) for frames in animations.values() for p in frames))
    if image:sources.append(Path(image).resolve(strict=True))
    if preset=='image' and not image:raise ValueError('请先生成或选择图片。')
    if preset=='audio' and not audio:raise ValueError('请先生成或选择音频。')
    sound=Path(audio).resolve(strict=True) if audio else None
    if sound and sound.suffix.lower() not in ('.wav','.ogg','.mp3'):raise ValueError('Godot音频请选择WAV、OGG或MP3。')
    size=None
    for path in sources:
        check()
        with Image.open(path) as im:
            if size and im.size!=size:raise ValueError('动画各帧尺寸需要一致。')
            size=im.size;im.verify()
    parent=root/'generated'/'ali_assets'
    if not parent.resolve().is_relative_to(root):raise ValueError('导出目录指向Godot项目之外。')
    slug=re.sub(r'[^A-Za-z0-9_-]','_',name.strip()).strip('_') or 'asset'
    folder=parent/(slug+'_'+uuid4().hex[:8]);folder.mkdir(parents=True,exist_ok=False)
    base='res://'+folder.relative_to(root).as_posix();external=[];resources=[];node=[];mapping={};hashes=[]
    def ext(kind,path,key):external.append(f'[ext_resource type="{kind}" path="{path}" id="{key}"]')
    for i,path in enumerate(sources):
        check();checksum=digest(path)
        target=folder/f'frame_{i:04d}.png'
        with Image.open(path) as im:
            im=im.convert('RGBA')
            if output_height:im=im.resize((max(1,round(im.width*output_height/im.height)),output_height),Image.Resampling.NEAREST)
            im.save(target);size=im.size
        if digest(path)!=checksum:raise ValueError('导出期间源素材变化，未发布组件。')
        key=f't{i}';mapping[path]=key;ext('Texture2D',base+'/'+target.name,key);hashes.append(dict(source=str(path),sha256=checksum,output=target.name))
    if sound:
        check();checksum=digest(sound)
        target=folder/('sound'+sound.suffix.lower());shutil.copy2(sound,target)
        if digest(target)!=checksum or digest(sound)!=checksum:raise ValueError('导出期间源音频变化，未发布组件。')
        kind='AudioStreamWAV' if target.suffix=='.wav' else 'AudioStreamOggVorbis' if target.suffix=='.ogg' else 'AudioStreamMP3'
        ext(kind,base+'/'+target.name,'sound');hashes.append(dict(source=str(sound),sha256=digest(sound),output=target.name))
    if animations:
        values=[]
        for animation,frames in animations.items():
            cells=','.join('{"duration":1.0,"texture":ExtResource("'+mapping[Path(p).resolve()]+'")} ' for p in frames)
            repeat=loop and not animation.startswith(('attack','jump','hurt','death','dash','roll','cast','interact','land'))
            values.append('{"name":&"'+animation+'","speed":'+str(float(fps))+',"loop":'+str(bool(repeat)).lower()+',"frames":['+cells+']}')
        resources.append('[sub_resource type="SpriteFrames" id="frames"]\nanimations = ['+','.join(values)+']')
    moving=preset in ('two_way','four_way','platformer')
    if moving:
        shutil.copy2(ADDON/'runtime'/'player.gd',folder/'player.gd');ext('Script',base+'/player.gd','player')
        shutil.copy2(ADDON/'runtime'/'blueprint_runtime.gd',folder/'blueprint_runtime.gd')
        shutil.copy2(ADDON/'addons'/'ali_assets'/'blueprint_model.gd',folder/'blueprint_model.gd')
        resources.append('[sub_resource type="CircleShape2D" id="body_shape"]\nradius = '+str(max(2,size[0]/6)))
        node=['[node name="GeneratedCharacter" type="CharacterBody2D"]','texture_filter = 1','motion_mode = 1','script = ExtResource("player")','four_way = '+str(preset=='four_way').lower(),
            '[node name="CollisionShape2D" type="CollisionShape2D" parent="."]','shape = SubResource("body_shape")']
        if preset=='platformer':node.insert(5,'platformer = true')
    elif preset=='audio':node=['[node name="GeneratedSound" type="AudioStreamPlayer2D"]','stream = ExtResource("sound")']
    else:node=['[node name="GeneratedAsset" type="Node2D"]','texture_filter = 1']
    if animations:
        first='walk_down' if preset=='four_way' else next(iter(animations))
        node+=['[node name="AnimatedSprite2D" type="AnimatedSprite2D" parent="."]','sprite_frames = SubResource("frames")',f'animation = &"{first}"',f'offset = Vector2(0, {-size[1]/2})']
        if preset=='animated':node+=['autoplay = "'+first+'"']
    if preset=='image':node+=['[node name="Sprite2D" type="Sprite2D" parent="."]','texture = ExtResource("'+mapping[Path(image).resolve()]+'")']
    if moving:
        node+=['[node name="Footsteps" type="AudioStreamPlayer2D" parent="."]']
        if sound:node+=['stream = ExtResource("sound")']
    scene=folder/'asset.tscn';scene.write_text('[gd_scene format=3]\n\n'+'\n\n'.join(external+resources)+'\n\n'+'\n'.join(node)+'\n','utf-8')
    record=dict(schema_version=1,name=name,preset=preset,scene=base+'/asset.tscn',fps=fps,loop=loop,files=hashes,
        animations={k:len(v) for k,v in animations.items()},footsteps=bool(sound and moving),original_files_modified=False)
    check();write_json(folder/'asset.json',record)
    return dict(folder=str(folder),scene=str(scene),resource=record['scene'],manifest=str(folder/'asset.json'))
