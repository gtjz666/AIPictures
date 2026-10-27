"""Fixed-reference side-view walk rig, geometric guides and real ComfyUI refinement.

This is a hybrid cutout/AI workflow calibrated to blue_side_v3, not a general rigging tool.
The website reference informed the action/sequence interaction, not these joint coordinates.
"""
import json
import math
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .action_intent import parse_intent
from .character_profile import JOINTS, JOINT_NAMES, character_workflow, paint_pose, rig_document, POSE_PROMPT, NEGATIVE
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


def walk_rig(phase, pace='normal'):
    """Phase 0..1; stance foot stays on the ground; mirrored legs are half a cycle apart."""
    t = (phase % 1) * math.tau
    rig = deepcopy(rig_document())
    bob = 3 * math.sin(t * 2)
    for name, point in rig['joints'].items(): point[1] += 14 + bob
    stride = {'slow': 62, 'normal': 78, 'fast': 88}[pace]
    for hip_i, knee_i, ankle_i, offset in [(8, 9, 10, 0), (11, 12, 13, math.pi)]:
        q = (t + offset) % math.tau
        hip = rig['joints'][JOINT_NAMES[hip_i]]
        ankle = [hip[0] + stride * math.cos(q), 910 - 38 * max(0, -math.sin(q)), 1]
        upper = math.dist(JOINTS[hip_i][:2], JOINTS[knee_i][:2])
        lower = math.dist(JOINTS[knee_i][:2], JOINTS[ankle_i][:2])
        rig['joints'][JOINT_NAMES[knee_i]] = knee_ik(hip, ankle, upper, lower)
        rig['joints'][JOINT_NAMES[ankle_i]] = ankle
    for shoulder_i, elbow_i, wrist_i, offset in [(2,3,4,0), (5,6,7,math.pi)]:
        shoulder = rig['joints'][JOINT_NAMES[shoulder_i]]
        angle = -.24 * math.cos(t + offset)
        upper = math.dist(JOINTS[shoulder_i][:2], JOINTS[elbow_i][:2])
        lower = math.dist(JOINTS[elbow_i][:2], JOINTS[wrist_i][:2])
        elbow = [shoulder[0] + upper * math.sin(angle), shoulder[1] + upper * math.cos(angle), 1]
        wrist = [elbow[0] + lower * math.sin(angle + .08), elbow[1] + lower * math.cos(angle + .08), 1]
        rig['joints'][JOINT_NAMES[elbow_i]] = elbow
        rig['joints'][JOINT_NAMES[wrist_i]] = wrist
    rig.update(phase=phase % 1, action='walk', bob=14+bob,
               stage=STAGES[int((phase % 1) * 8) % 8], ground_y=978)
    return rig


def foreground(image):
    """Remove only border-connected pale blue. Internal blue hair remains opaque."""
    rgb = image.convert('RGB'); r,g,b = rgb.split()
    mask = ImageChops.multiply(b.point(lambda v: 255 if v > 150 else 0),
                              g.point(lambda v: 255 if v > 130 else 0))
    mask = ImageChops.multiply(mask, ImageChops.subtract(b,r).point(lambda v: 255 if v > 15 else 0))
    mask = ImageChops.multiply(mask, ImageChops.subtract(g,r).point(lambda v: 255 if v > 5 else 0))
    # The source has a continuous background; flood fill avoids deleting blue details.
    ImageDraw.floodfill(mask, (0,0), 128)
    alpha = mask.point(lambda v: 0 if v == 128 else 255)
    output = rgb.convert('RGBA'); output.putalpha(alpha); return output


def polygon(points):
    mask = Image.new('L', SIZE); ImageDraw.Draw(mask).polygon(points, fill=255); return mask


def part(image, mask):
    output = image.copy(); output.putalpha(ImageChops.multiply(output.getchannel('A'), mask)); return output


def segment(image, source_a, source_b, target_a, target_b):
    angle = math.atan2(target_b[1]-target_a[1], target_b[0]-target_a[0]) - math.atan2(source_b[1]-source_a[1], source_b[0]-source_a[0])
    scale = math.dist(target_a[:2],target_b[:2]) / math.dist(source_a[:2],source_b[:2])
    a, b = math.cos(angle)/scale, math.sin(angle)/scale
    c = source_a[0] - a*target_a[0] - b*target_a[1]
    d, e = -b, a
    f = source_a[1] - d*target_a[0] - e*target_a[1]
    return image.transform(SIZE, Image.Transform.AFFINE, (a,b,c,d,e,f), Image.Resampling.BICUBIC)


class ReferenceCutout:
    def __init__(self, reference):
        self.source = foreground(Image.open(reference).resize(SIZE, Image.Resampling.LANCZOS))
        # Explicit annotation for this reference only; no automatic segmentation claim.
        arm_mask = polygon([(350,241),(372,247),(388,294),(389,383),(395,491),(394,534),
                            (389,576),(376,590),(362,585),(355,550),(343,518),(337,456),(334,377),(331,294)])
        leg_mask = polygon([(347,595),(413,595),(395,693),(385,763),(379,816),(377,909),
                            (382,936),(411,943),(458,956),(458,979),(329,979),(327,947),(338,909),
                            (335,815),(338,761),(350,696)])
        arm, leg = part(self.source, arm_mask), part(self.source, leg_mask)
        def band(y0,y1): return polygon([(0,y0),(768,y0),(768,y1),(0,y1)])
        self.upper_arm = part(arm, band(0,403)); self.lower_arm = part(arm,band(380,1024))
        self.thigh = part(leg,band(0,740)); self.shin = part(leg,band(714,918)); self.shoe = part(leg,band(898,1024))
        remove = ImageChops.lighter(arm_mask, band(594,1024))
        body = part(self.source, ImageChops.invert(remove))
        patches = Image.new('RGBA',SIZE); draw = ImageDraw.Draw(patches)
        draw.polygon([(345,253),(381,249),(426,287),(445,375),(420,409),(344,409)],fill=(237,237,234),outline=(32,36,44),width=2)
        draw.polygon([(345,394),(439,394),(447,591),(326,591)],fill=(31,36,49),outline=(27,29,38),width=2)
        patches.alpha_composite(body); self.body = patches

    def render(self, rig):
        joints = rig['joints']; p = lambda i: joints[JOINT_NAMES[i]]
        canvas = Image.new('RGBA', SIZE)
        limbs_mask = Image.new('L',SIZE)
        shoes_mask = Image.new('L',SIZE)
        def paste(layer, moving=True, far=False, shoe=False):
            nonlocal limbs_mask, shoes_mask
            if far: layer = ImageEnhance.Brightness(layer).enhance(.90)
            canvas.alpha_composite(layer)
            if moving: limbs_mask = ImageChops.lighter(limbs_mask, layer.getchannel('A'))
            if shoe: shoes_mask = ImageChops.lighter(shoes_mask,layer.getchannel('A'))
        for shoulder,elbow,wrist,hip,knee,ankle,far in [(5,6,7,11,12,13,True),(2,3,4,8,9,10,False)]:
            if not far:
                body = self.body.transform(SIZE,Image.Transform.AFFINE,(1,0,0,0,1,-rig['bob']),Image.Resampling.BICUBIC)
                paste(body,False)
            paste(segment(self.upper_arm,JOINTS[2],JOINTS[3],p(shoulder),p(elbow)),far=far)
            paste(segment(self.lower_arm,JOINTS[3],JOINTS[4],p(elbow),p(wrist)),far=far)
            paste(segment(self.thigh,JOINTS[8],JOINTS[9],p(hip),p(knee)),far=far)
            paste(segment(self.shin,JOINTS[9],JOINTS[10],p(knee),p(ankle)),far=far)
            # Keep shoe orientation level: support foot has a stable sole/ground line.
            ankle_p = p(ankle); shoe = self.shoe.transform(SIZE,Image.Transform.AFFINE,
                (1,0,JOINTS[10][0]-ankle_p[0],0,1,JOINTS[10][1]-ankle_p[1]),Image.Resampling.BICUBIC)
            paste(shoe,False,far,True)
        # Preserve source head/torso and shoe pixels; only repair limb seams with AI.
        body_alpha = body.getchannel('A')
        repair = ImageChops.subtract(limbs_mask,body_alpha)
        repair = ImageChops.subtract(repair,shoes_mask).filter(ImageFilter.GaussianBlur(2))
        guide = Image.new('RGB',SIZE,(188,220,250)); guide.paste(canvas,mask=canvas.getchannel('A'))
        return guide, canvas.getchannel('A'), repair


def frame_workflow(reference_name, pose_name, guide_name, seed, positive, checkpoint, steps=20):
    graph = character_workflow(reference_name, pose_name)
    graph.pop('4',None)
    graph['30'] = {'class_type':'LoadImage','inputs':{'image':guide_name},'_meta':{'title':'当前帧骨骼预变形参考'}}
    graph['31'] = {'class_type':'VAEEncodeTiled','inputs':{'pixels':['30',0],'vae':['1',2],
                   'tile_size':512,'overlap':64,'temporal_size':64,'temporal_overlap':8}}
    graph['5']['inputs'].update(latent_image=['31',0],seed=seed,denoise=.35,steps=steps,cfg=4.5)
    graph['1']['inputs']['ckpt_name'] = checkpoint
    graph['2']['inputs']['text'] = positive
    graph['3']['inputs']['text'] = NEGATIVE + ', white socks, boots, changed shoes, motion blur, speed lines'
    graph['13']['inputs']['weight'] = .9
    graph['22']['inputs']['strength'] = .75
    return graph


def export_sequence(folder, frames, fps):
    folder = Path(folder); images = []
    try:
        images = [Image.open(path).convert('RGBA') for path in frames]
        columns = min(4,len(images)); rows = math.ceil(len(images)/columns)
        sheet = Image.new('RGBA',(SIZE[0]*columns,SIZE[1]*rows))
        for i,image in enumerate(images): sheet.paste(image,((i%columns)*SIZE[0],(i//columns)*SIZE[1]))
        sheet.save(folder/'sprite_sheet.png')
        previews = []
        for image in images:
            small=image.resize((384,512),Image.Resampling.LANCZOS)
            preview=small.convert('RGB').quantize(colors=255)
            preview.paste(255,mask=small.getchannel('A').point(lambda a:255 if a<128 else 0))
            preview.info['transparency']=255; previews.append(preview)
        previews[0].save(folder/'walk.gif',save_all=True,append_images=previews[1:],duration=round(1000/fps),
                         loop=0,disposal=2,transparency=255,optimize=False)
        return {'sprite_sheet':'sprite_sheet.png','gif':'walk.gif','columns':columns,'rows':rows,
                'cell_size':list(SIZE),'gif_size':[384,512],'background':'transparent','gif_transparency':'binary'}
    finally:
        for image in images: image.close()


def new_sequence():
    folder = DATA/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
    folder.mkdir(parents=True); return folder


def generate_walk(client, folder, profile, prompt, checkpoint, seed, count, fps, emit, cancel, steps=20):
    """Sequential GPU jobs, immutable frame graphs, partial results survive cancellation."""
    folder = Path(folder); intent = parse_intent(prompt)
    if count not in (8,16): raise ValueError('当前支持 8 或 16 帧行走周期')
    if not 1 <= fps <= 30: raise ValueError('播放帧率范围为 1–30')
    if intent.action in ('run','jump','reach','stand') or ('walk' in intent.negated and intent.action != 'walk'):
        raise ValueError('当前选择了人物行走动画帧，请输入行走要求；其他动作请使用单张图片。')
    manifest = {'schema_version':1,'kind':'walk','status':'preparing','fps':fps,'frame_count':count,
        'canvas':list(SIZE),'ground_y':978,'seed':seed,'user_prompt':prompt,'intent':intent.to_dict(),
        'reference_sha256':digest(profile['reference']),'reference':profile['reference'],
        'method':'reference_cutout_controlnet_ipadapter_limb_refinement','steps':steps,'frames':[],
        'notes':'仅为此侧视基准人工分层；遮挡侧肢体由可见侧估计。AI 修复肢体，头身和鞋保留参考像素。'}
    save = lambda: write_json(folder/'sequence.json',manifest)
    save()
    def checked():
        if cancel.is_set(): raise Cancelled('行走序列已取消，已生成的帧保留在本地')
    try:
        checked(); cutout = ReferenceCutout(profile['reference'])
        ref_name = client.upload_image(profile['reference'])
        for i in range(count):
            checked(); frame = folder/f'frame_{i:03d}'; frame.mkdir(exist_ok=True)
            rig = walk_rig(i/count,intent.pace); write_json(frame/'pose.json',rig)
            paint_pose(rig).save(str(frame/'pose.png'))
            guide,alpha,repair = cutout.render(rig)
            guide.save(frame/'guide.png'); alpha.save(frame/'alpha.png'); repair.save(frame/'repair_mask.png')
            checked(); pose_name = client.upload_image(frame/'pose.png'); guide_name = client.upload_image(frame/'guide.png')
            positive = POSE_PROMPT + ', ' + 'one frame of a seamless walk cycle, ' + intent.english
            # Render facing right; left-facing output is a deterministic final mirror.
            graph = frame_workflow(ref_name,pose_name,guide_name,seed,positive,checkpoint,steps)
            write_json(frame/'workflow.json',graph)
            manifest['status']='running'; save()
            emit('frame_started',{'index':i,'count':count,'stage':rig['stage']})
            def relay(kind,data):
                emit('frame_event',{'index':i,'count':count,'event':kind,'data':data})
            result = client.generate(graph,frame,relay,cancel,
                submitted=lambda pid: write_json(frame/'submitted.json',{'prompt_id':pid}))
            write_json(frame/'result.json',result); checked()
            with Image.open(result['images'][0]) as raw:
                refined = Image.composite(raw.convert('RGB').resize(SIZE),guide,repair).convert('RGBA')
            refined.putalpha(alpha)
            if intent.direction == 'left': refined = ImageOps.mirror(refined)
            output = folder/f'frame_{i:03d}.png'; refined.save(output)
            manifest['frames'].append({'index':i,'image':output.name,'pose':f'frame_{i:03d}/pose.json',
                'workflow':f'frame_{i:03d}/workflow.json','prompt_id':result['prompt_id'],'stage':rig['stage'],
                'phase':i/count,'mirrored':intent.direction=='left'})
            save(); emit('frame_ready',{'index':i,'count':count,'image':str(output)})
        checked()
        manifest['exports'] = export_sequence(folder,[folder/f['image'] for f in manifest['frames']],fps)
        manifest['status']='completed'; save()
        return {'manifest':str(folder/'sequence.json'),'frames':[str(folder/f['image']) for f in manifest['frames']],
                'gif':str(folder/'walk.gif'),'sprite_sheet':str(folder/'sprite_sheet.png')}
    except Exception as exc:
        manifest['status']='cancelled' if isinstance(exc,Cancelled) else 'failed'
        manifest['error']=str(exc); save(); raise
