"""Game state clips and an optional physics demonstration from unchanged sprite frames."""
from pathlib import Path
from PIL import Image
from .storage import write_json
from .gif_export import save_gif


def preview_offset(phase: float, height: int=160,liftoff:float=.14,landing:float=.80) -> int:
    if not liftoff<phase<landing:return 0
    t=(phase-liftoff)/(landing-liftoff)
    return -round(height*4*t*(1-t))


def game_metadata(action, frames, fps,revision=4):
    phases=[frame['phase'] for frame in frames]
    groups=({'takeoff':(0,.18),'rise':(.18,.38),'apex':(.38,.62),'fall':(.62,.80),'land':(.80,1.01)} if action=='jump' else
            {'startup':(0,.30),'active':(.30,.46),'recovery':(.46,1.01)} if action=='attack' else {})
    if revision>=5:
        groups=({'takeoff':(0,.26),'rise':(.26,.40),'apex':(.40,.52),'fall':(.52,.70),'land':(.70,1.01)} if action=='jump' else
                {'startup':(0,.34),'active':(.34,.47),'recovery':(.47,1.01)} if action=='attack' else {})
    liftoff,landing=(.26,.70) if revision>=5 else (.14,.80)
    return {'schema_version':1,'action':action,'root_motion_baked':False,'pivot':[384,978],
        'units':'pixels','clips':{name:[i for i,p in enumerate(phases) if a<=p<b] for name,(a,b) in groups.items()},
        'fps':fps,'phase_times':phases,'engine_driven_jump':action=='jump',
        'motion_revision':revision,'preview_only':{'top_padding':192,'height':160,'liftoff':liftoff,'landing':landing,
            'offset_y':[preview_offset(p,liftoff=liftoff,landing=landing) if action=='jump' else 0 for p in phases]},
        'note':'游戏引擎控制角色整体位移；PNG 不包含预览轨迹。攻击有效帧只作美术标记，游戏逻辑自行配置碰撞。'}


def export_game_data(folder, manifest):
    if manifest['action'] not in ('jump','attack'):return
    folder=Path(folder);data=game_metadata(manifest['action'],manifest['frames'],manifest['fps'],manifest.get('motion_revision',4))
    manifest['game_animation']=data;write_json(folder/'game_animation.json',data)
    manifest['exports']['game_metadata']='game_animation.json'
    if manifest['action']=='jump':
        images=[]
        for frame,dy in zip(manifest['frames'],data['preview_only']['offset_y']):
            with Image.open(folder/frame['image']) as source:
                canvas=Image.new('RGBA',(source.width,source.height+192))
                canvas.paste(source,(0,192+dy));images.append(canvas)
        save_gif(images,folder/'jump_game_preview.gif',manifest['fps'],loop=True,size=(384,608))
        manifest['exports']['game_preview_gif']='jump_game_preview.gif'
