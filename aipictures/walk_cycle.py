"""Reference-adapted side-view walk rigs with continuous source-color meshes and ComfyUI."""
import json
import math
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from .action_intent import walk_intent
from .prompt_text import negative_text
from .character_profile import JOINT_NAMES, character_workflow, paint_pose, rig_document, NEGATIVE
from .engine import Cancelled
from .storage import DATA, write_json
from .workflow_library import digest

SIZE = (768, 1024)
STAGES = ('右脚接触', '右脚承重', '左腿经过', '左脚前摆', '左脚接触', '左脚承重', '右腿经过', '右脚前摆')


def knee_ik(hip, ankle, upper, lower):
    dx, dy = ankle[0] - hip[0], ankle[1] - hip[1]
    distance = math.hypot(dx, dy)
    if not abs(upper - lower) < distance < upper + lower:
        raise ValueError('行走骨骼目标超出腿长，请缩小步幅')
    along = (upper * upper - lower * lower + distance * distance) / (2 * distance)
    bend = math.sqrt(max(0, upper * upper - along * along))
    return [hip[0] + along * dx / distance + bend * dy / distance,
            hip[1] + along * dy / distance - bend * dx / distance, 1]


def walk_rig(phase, pace='normal', base_rig=None):
    """Phase 0..1; stance foot stays on the ground; mirrored legs are half a cycle apart."""
    t = (phase % 1) * math.tau
    rig = deepcopy(base_rig or rig_document())
    source=[rig['joints'][name][:] for name in JOINT_NAMES]
    length=math.dist(source[8][:2],source[9][:2])+math.dist(source[9][:2],source[10][:2])
    drop=max(0,source[10][1]-source[8][1]-.975*length) if base_rig else 14
    bob=drop+3*math.sin(t*2)
    for name, point in rig['joints'].items(): point[1] += bob
    stride=({'slow':.14,'normal':.18,'fast':.21}[pace]*length if base_rig else {'slow':62,'normal':78,'fast':88}[pace])
    for hip_i, knee_i, ankle_i, offset in [(8, 9, 10, 0), (11, 12, 13, math.pi)]:
        q = (t + offset) % math.tau
        hip = rig['joints'][JOINT_NAMES[hip_i]]
        ground_ankle=source[ankle_i][1] if base_rig else 910
        ankle = [hip[0] + stride * math.cos(q), ground_ankle - length*.09 * max(0, -math.sin(q)), source[ankle_i][2]]
        upper = math.dist(source[hip_i][:2], source[knee_i][:2])
        lower = math.dist(source[knee_i][:2], source[ankle_i][:2])
        if base_rig:
            # Keep planted feet on the floor while limiting stride to this character's reach.
            vertical=ankle[1]-hip[1]; reach=upper+lower-.001
            horizontal=math.sqrt(max(0,reach*reach-vertical*vertical))
            ankle[0]=hip[0]+max(-horizontal,min(horizontal,ankle[0]-hip[0]))
        rig['joints'][JOINT_NAMES[knee_i]] = knee_ik(hip, ankle, upper, lower)
        rig['joints'][JOINT_NAMES[ankle_i]] = ankle
    for shoulder_i, elbow_i, wrist_i, offset in [(2,3,4,0), (5,6,7,math.pi)]:
        shoulder = rig['joints'][JOINT_NAMES[shoulder_i]]
        angle = -.24 * math.cos(t + offset)
        upper = math.dist(source[shoulder_i][:2], source[elbow_i][:2])
        lower = math.dist(source[elbow_i][:2], source[wrist_i][:2])
        elbow = [shoulder[0] + upper * math.sin(angle), shoulder[1] + upper * math.cos(angle), 1]
        wrist = [elbow[0] + lower * math.sin(angle + .08), elbow[1] + lower * math.cos(angle + .08), 1]
        rig['joints'][JOINT_NAMES[elbow_i]] = elbow
        rig['joints'][JOINT_NAMES[wrist_i]] = wrist
    rig.update(phase=phase % 1, action='walk', bob=bob,
               stage=STAGES[int((phase % 1) * 8) % 8], ground_y=978)
    return rig


def frame_workflow(reference_name, pose_name, guide_name, seed, positive, checkpoint, steps=20, negative=None):
    graph = character_workflow(reference_name, pose_name)
    graph.pop('4',None)
    graph['30'] = {'class_type':'LoadImage','inputs':{'image':guide_name},'_meta':{'title':'当前帧骨骼预变形参考'}}
    graph['31'] = {'class_type':'VAEEncodeTiled','inputs':{'pixels':['30',0],'vae':['1',2],
                   'tile_size':512,'overlap':64,'temporal_size':64,'temporal_overlap':8}}
    graph['5']['inputs'].update(latent_image=['31',0],seed=seed,denoise=.35,steps=steps,cfg=4.5)
    graph['1']['inputs']['ckpt_name'] = checkpoint
    graph['2']['inputs']['text'] = positive
    graph['3']['inputs']['text'] = negative_text(NEGATIVE if negative is None else negative)[0]
    graph['13']['inputs']['weight'] = .9
    graph['22']['inputs']['strength'] = .75
    return graph


def export_sequence(folder, frames, fps, name='walk'):
    if name not in ('walk','idle','run','jump','squat','reach'): raise ValueError('未知动作导出名称。')
    folder = Path(folder); images = []
    try:
        images = [Image.open(path).convert('RGBA') for path in frames]
        columns = min(4,len(images)); rows = math.ceil(len(images)/columns)
        sheet = Image.new('RGBA',(SIZE[0]*columns,SIZE[1]*rows))
        for i,image in enumerate(images): sheet.paste(image,((i%columns)*SIZE[0],(i//columns)*SIZE[1]))
        sheet.save(folder/'sprite_sheet.png')
        import numpy as np
        from scipy.spatial import cKDTree
        samples=[]
        for image in images:
            array=np.asarray(image); samples.append(array[:,:,:3][array[:,:,3]>200][::4])
        colors=np.concatenate(samples) if any(len(sample) for sample in samples) else np.zeros((1,3),dtype=np.uint8)
        colors=colors[np.linspace(0,len(colors)-1,min(65536,len(colors)),dtype=int)]
        palette=Image.fromarray(np.resize(colors,(256,256,3))).quantize(colors=255,method=Image.Quantize.MEDIANCUT)
        palette_colors=np.asarray(palette.getpalette(),dtype=float).reshape(-1,3)[:255]
        tree=cKDTree(palette_colors)
        table=palette.getpalette(); table=table+[0]*(768-len(table))
        previews = []
        for image in images:
            small=image.resize((384,512),Image.Resampling.LANCZOS)
            preview=small.convert('RGB').quantize(palette=palette,dither=Image.Dither.NONE)
            indices=np.array(preview); reserved=indices==255
            if reserved.any(): indices[reserved]=tree.query(np.asarray(small)[:,:,:3][reserved])[1]
            indices[np.asarray(small.getchannel('A'))<128]=255
            preview=Image.fromarray(indices); preview.putpalette(table)
            preview.info['transparency']=255; previews.append(preview)
        repeat={} if name in ('jump','squat') else {'loop':0}
        previews[0].save(folder/(name+'.gif'),save_all=True,append_images=previews[1:],duration=round(1000/fps),
                         disposal=2,transparency=255,optimize=False,**repeat)
        return {'sprite_sheet':'sprite_sheet.png','gif':name+'.gif','columns':columns,'rows':rows,
                'cell_size':list(SIZE),'gif_size':[384,512],'background':'transparent','gif_transparency':'binary',
                'gif_palette':'shared_foreground_palette','loop':name not in ('jump','squat')}
    finally:
        for image in images: image.close()


def new_sequence():
    folder = DATA/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
    folder.mkdir(parents=True); return folder


def generate_walk(client, folder, profile, prompt, checkpoint, seed, count, fps, emit, cancel, steps=20, negative=None, reference=None):
    """Sequential GPU jobs, immutable frame graphs, partial results survive cancellation."""
    folder = Path(folder); intent = walk_intent(prompt)
    if count not in (8,16): raise ValueError('当前支持 8 或 16 帧行走周期')
    if not 1 <= fps <= 30: raise ValueError('播放帧率范围为 1–30')
    reference=reference or profile['reference']
    manifest = {'schema_version':2,'kind':'walk','status':'preparing','fps':fps,'frame_count':count,
        'canvas':list(SIZE),'ground_y':978,'seed':seed,'user_prompt':prompt,'intent':intent.to_dict(),
        'reference_sha256':digest(reference),'reference':str(reference),
        'method':'detected_rig_continuous_mesh_color_bounded_refinement','steps':steps,'negative':negative,'frames':[],
        'notes':'按导入图识别可见关节和主体；遮挡侧估计。共享原图颜色及透明遮罩，仅对关节接缝补充局部细节。'}
    save = lambda: write_json(folder/'sequence.json',manifest)
    save()
    def checked():
        if cancel.is_set(): raise Cancelled('行走序列已取消，已生成的帧保留在本地')
    try:
        from .reference_analysis import prepare_reference,REFERENCE_POSITIVE
        from .skin_warp import AdaptiveCutout,refine_preserving_color
        checked(); analysis=prepare_reference(reference,client,emit,cancel)
        write_json(folder/'reference_analysis.json',analysis)
        cutout=AdaptiveCutout(analysis)
        write_json(folder/'source_rig.json',cutout.rig); manifest['layers']=cutout.metadata
        manifest['source_direction']=analysis['direction']
        ref_name = client.upload_image(analysis['opaque'])
        for i in range(count):
            checked(); frame = folder/f'frame_{i:03d}'; frame.mkdir(exist_ok=True)
            rig = walk_rig(i/count,intent.pace,cutout.rig); write_json(frame/'pose.json',rig)
            paint_pose(rig).save(str(frame/'pose.png'))
            guide,alpha,repair = cutout.render(rig)
            guide.save(frame/'guide.png'); alpha.save(frame/'alpha.png'); repair.save(frame/'repair_mask.png')
            checked(); pose_name = client.upload_image(frame/'pose.png'); guide_name = client.upload_image(frame/'guide.png')
            positive = REFERENCE_POSITIVE + ', one frame of a seamless walk cycle, body pose matching the OpenPose map, ' + intent.english
            # Render facing right; left-facing output is a deterministic final mirror.
            graph = frame_workflow(ref_name,pose_name,guide_name,seed,positive,checkpoint,steps,negative)
            write_json(frame/'workflow.json',graph)
            manifest['status']='running'; save()
            emit('frame_started',{'index':i,'count':count,'stage':rig['stage']})
            def relay(kind,data):
                emit('frame_event',{'index':i,'count':count,'event':kind,'data':data})
            result = client.generate(graph,frame,relay,cancel,
                submitted=lambda pid: write_json(frame/'submitted.json',{'prompt_id':pid}))
            write_json(frame/'result.json',result); checked()
            with Image.open(result['images'][0]) as raw:
                refined,quality = refine_preserving_color(raw,guide,alpha,repair,cutout.last_rgba)
            write_json(frame/'quality.json',quality)
            if intent.direction == 'left': refined = ImageOps.mirror(refined)
            output = folder/f'frame_{i:03d}.png'; refined.save(output)
            manifest['frames'].append({'index':i,'image':output.name,'pose':f'frame_{i:03d}/pose.json',
                'workflow':f'frame_{i:03d}/workflow.json','prompt_id':result['prompt_id'],'stage':rig['stage'],
                'phase':i/count,'mirrored':intent.direction=='left','quality':quality})
            save(); emit('frame_ready',{'index':i,'count':count,'image':str(output)})
        checked()
        manifest['exports'] = export_sequence(folder,[folder/f['image'] for f in manifest['frames']],fps)
        manifest['status']='completed'; save()
        return {'manifest':str(folder/'sequence.json'),'frames':[str(folder/f['image']) for f in manifest['frames']],
                'gif':str(folder/'walk.gif'),'sprite_sheet':str(folder/'sprite_sheet.png')}
    except Exception as exc:
        manifest['status']='cancelled' if isinstance(exc,Cancelled) else 'failed'
        manifest['error']=str(exc); save(); raise
