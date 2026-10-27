"""Versioned, manually calibrated side-view character rig and workflow recipes."""
import json
import math
import shutil
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from .storage import DATA, write_json
from .workflow import ImageRequest, build_workflow
from .prompt_binding import add_image_input
from .workflow_library import digest

PROFILE_ROOT = DATA / 'characters' / 'blue_side_v3'
PROFILE_FILE = PROFILE_ROOT / 'profile.json'
ACTIVE_PROFILE_FILE=DATA/'characters'/'active-profile.json'
POSITIVE = (
    'one single full-body 2D anime character, exact same character as the supplied reference image, '
    'strict 90 degree right-facing side profile, short dark navy-blue bob hair with layered ends, '
    'two slim dark hair clips behind the visible ear, one visible yellow-green eye, fair skin, '
    'white long-sleeve collared blouse, thin black ribbon tie, dark navy suspenders, '
    'high-waisted dark navy pleated skirt ending above the knees, dark knee-high socks, brown loafers, '
    'slender proportions matching the reference, clean precise dark outlines, soft flat cel shading, '
    'neutral upright standing pose with relaxed arm, fixed full-body framing from hair to both shoes, '
    'feet on a consistent ground line, centered, plain pale-blue background, preserve the same hairstyle, '
    'outfit, silhouette, body proportions, camera angle and illustration style'
)
NEGATIVE = (
    'different character, different hairstyle, long hair, blonde hair, red hair, changed outfit, '
    'jacket, coat, cape, armor, trousers, bare feet, high heels, hat, weapons, accessories, '
    'front view, back view, three-quarter view, facing left, looking at camera, perspective distortion, '
    'portrait, close-up, cropped head, cropped shoes, out of frame, character sheet, turnaround sheet, '
    'multiple panels, duplicate character, multiple people, extra arms, extra legs, extra fingers, '
    'missing limbs, twisted joints, bad hands, deformed anatomy, floating feet, visible skeleton, bones, '
    'x-ray, photorealistic, 3d render, painterly brush texture, detailed scenery, text, watermark, logo, blurry'
)
POSE_PROMPT = POSITIVE.replace('neutral upright standing pose with relaxed arm, ',
                             'body pose and limb arrangement matching the supplied OpenPose map, ')

# OpenPose BODY_18 order; occluded far-side joints are estimates, not detections.
JOINT_NAMES = ['nose', 'neck', 'right_shoulder', 'right_elbow', 'right_wrist',
    'left_shoulder', 'left_elbow', 'left_wrist', 'right_hip', 'right_knee', 'right_ankle',
    'left_hip', 'left_knee', 'left_ankle', 'right_eye', 'left_eye', 'right_ear', 'left_ear']
JOINTS = [(440, 151, 1), (377, 215, 1), (354, 246, 1), (359, 392, 1), (367, 527, 1),
    (382, 242, .35), (389, 388, .35), (393, 522, .35), (374, 502, .65), (384, 727, 1),
    (362, 910, 1), (397, 500, .3), (403, 726, .35), (391, 909, .35),
    (417, 125, 1), (419, 126, .15), (360, 138, 1), (365, 139, .15)]
LIMBS = [(1,2),(1,5),(2,3),(3,4),(5,6),(6,7),(1,8),(8,9),(9,10),
         (1,11),(11,12),(12,13),(1,0),(0,14),(14,16),(0,15),(15,17)]
COLORS = ['#ff0000','#ff5500','#ffaa00','#ffff00','#aaff00','#55ff00',
          '#00ff00','#00ff55','#00ffaa','#00ffff','#00aaff','#0055ff',
          '#0000ff','#5500ff','#aa00ff','#ff00ff','#ff00aa','#ff0055']


def rig_document():
    return {'schema_version': 3, 'rig_id': 'blue_side_right_v3', 'canvas': [768, 1024],
            'direction': 'right', 'ground_y': 978, 'annotation': 'manual_reference_calibration',
            'notes': '人工按参考图标定；遮挡的远侧关节为估计值，置信度降低。并非自动识别或已验证的动画绑定。',
            'openpose_order': JOINT_NAMES, 'joints': {name: list(point) for name, point in zip(JOINT_NAMES, JOINTS)},
            'limbs': [list(pair) for pair in LIMBS],
            'anchors': {'near_heel': [333, 961], 'near_toe': [455, 973], 'far_toe': [463, 958]}}


def pose_presets():
    standing = rig_document()
    reach = deepcopy(standing)
    # Forward kinematics with the same upper/lower arm lengths as the baseline.
    shoulder = reach['joints']['right_shoulder']
    upper = math.dist(JOINTS[2][:2], JOINTS[3][:2]); lower = math.dist(JOINTS[3][:2], JOINTS[4][:2])
    reach['joints']['right_elbow'] = [shoulder[0] + upper * .78, shoulder[1] + upper * .626, 1]
    elbow = reach['joints']['right_elbow']
    reach['joints']['right_wrist'] = [elbow[0] + lower * .98, elbow[1] - lower * .199, 1]
    return {'stand': {'title': '侧视站立 · 基准', 'rig': standing},
            'reach': {'title': '向前伸手 · 姿态草案', 'rig': reach}}


def paint_pose(rig, background=None):
    image = QImage(768, 1024, QImage.Format.Format_RGB32)
    image.fill(QColor('#000000'))
    painter = QPainter(image); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if background:
        painter.drawImage(image.rect(), QImage(str(background)))
        painter.fillRect(image.rect(), QColor(0, 0, 0, 100))
    points = [rig['joints'][name] for name in JOINT_NAMES]
    for i, (a, b) in enumerate(LIMBS):
        color = QColor(COLORS[i % len(COLORS)])
        if min(points[a][2], points[b][2]) < .5: color = color.darker(160)
        painter.setPen(QPen(color, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(*points[a][:2]), QPointF(*points[b][:2]))
    for i, point in enumerate(points):
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(COLORS[i]))
        painter.drawEllipse(QPointF(*point[:2]), 6, 6)
    painter.end()
    return image


def character_workflow(reference, pose=None):
    r = ImageRequest('sd_xl_base_1.0_0.9vae.safetensors', POSE_PROMPT if pose else POSITIVE,
                     NEGATIVE, 768, 1024, 28, 5.5, 20261026, 'dpmpp_2m', 'karras')
    graph = build_workflow(r)
    if not pose:
        add_image_input(graph, reference, 768, 1024, .3)
        del graph['4']
    else: graph['8'] = {'class_type': 'LoadImage', 'inputs': {'image': reference}}
    # Load weights explicitly; do not depend on a plugin's implicit preset model lookup.
    graph['11'] = {'class_type': 'IPAdapterModelLoader', 'inputs': {'ipadapter_file': 'ip-adapter-plus_sdxl_vit-h.safetensors'}}
    graph['12'] = {'class_type': 'CLIPVisionLoader', 'inputs': {'clip_name': 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'}}
    graph['13'] = {'class_type': 'IPAdapterAdvanced', 'inputs': {'model': ['1',0], 'ipadapter': ['11',0],
        'image': ['8',0], 'clip_vision': ['12',0], 'weight': .7, 'weight_type': 'linear',
        'combine_embeds': 'concat', 'start_at': 0., 'end_at': .85, 'embeds_scaling': 'V only'}}
    graph['5']['inputs']['model'] = ['13',0]
    if pose:
        graph['20'] = {'class_type': 'ControlNetLoader', 'inputs': {'control_net_name': 'controlnet-openpose-sdxl-1.0-xinsir.safetensors'}}
        graph['21'] = {'class_type': 'LoadImage', 'inputs': {'image': pose}, '_meta': {'title': '骨骼条件图（独立于角色参考）'}}
        graph['22'] = {'class_type': 'ControlNetApplyAdvanced', 'inputs': {'positive': ['2',0], 'negative': ['3',0],
            'control_net': ['20',0], 'image': ['21',0], 'vae': ['1',2], 'strength': .85, 'start_percent': 0., 'end_percent': .9}}
        graph['5']['inputs'].update(positive=['22',0], negative=['22',1])
    # Bound VAE activation memory when identity adapters share a 12GB GPU.
    graph['6']['class_type'] = 'VAEDecodeTiled'
    graph['6']['inputs'].update(tile_size=512, overlap=64, temporal_size=64, temporal_overlap=8)
    if not pose:
        graph['10']['class_type'] = 'VAEEncodeTiled'
        graph['10']['inputs'].update(tile_size=512, overlap=64, temporal_size=64, temporal_overlap=8)
    return graph


def install_profile(reference, client):
    reference = Path(reference)
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    target = PROFILE_ROOT / 'reference.png'
    checksum = digest(reference)
    if target.exists() and digest(target) != checksum:
        raise ValueError('该角色基准已存在不同图片，请先另建版本。')
    if not target.exists(): shutil.copy2(reference, target)
    server_ref = client.upload_image(target)
    presets = pose_presets(); paths = {}
    for key, preset in presets.items():
        folder = PROFILE_ROOT / 'poses'; folder.mkdir(exist_ok=True)
        write_json(folder / (key + '.json'), preset['rig'])
        pose_image = folder / (key + '.png'); paint_pose(preset['rig']).save(str(pose_image))
        paint_pose(preset['rig'], target).save(str(folder / (key + '_overlay.png')))
        server_pose = client.upload_image(pose_image)
        pose_workflow = character_workflow(server_ref, server_pose)
        path = PROFILE_ROOT / ('pose_' + key + '_api.json'); write_json(path, pose_workflow)
        paths[key] = {'title': preset['title'], 'graph': str(path), 'image': str(pose_image),
                      'overlay': str(folder / (key + '_overlay.png')), 'rig': str(folder / (key + '.json'))}
    graph = character_workflow(server_ref)
    write_json(PROFILE_ROOT / 'baseline_api.json', graph)
    profile = {'schema_version': 1, 'id': 'blue_side_v3', 'title': '蓝发侧视角色 · 基准 v3',
               'reference': str(target), 'source_sha256': checksum, 'width': 768, 'height': 1024,
               'positive': POSITIVE, 'pose_positive': POSE_PROMPT, 'negative': NEGATIVE,
               'baseline_graph': str(PROFILE_ROOT / 'baseline_api.json'), 'poses': paths,
               'default_denoise': .3, 'pose_requires': 'controlnet-openpose-sdxl-1.0-xinsir.safetensors'}
    write_json(PROFILE_FILE, profile)
    write_json(PROFILE_ROOT / 'rig_v3.json', rig_document())
    write_json(DATA / 'chat' / 'active-workflow.json', {'graph': graph, 'title': profile['title'],
        'character_id': profile['id'], 'route': 'baseline'})
    return profile


def load_profile():
    path=PROFILE_FILE
    if ACTIVE_PROFILE_FILE.exists(): path=Path(json.loads(ACTIVE_PROFILE_FILE.read_text('utf-8'))['profile'])
    return json.loads(path.read_text('utf-8')) if path.exists() else None


def install_adaptive_profile(reference,client,title='侧视人物参考'):
    """Add a versioned reference without overwriting the original blue character."""
    from .reference_analysis import prepare_reference,REFERENCE_POSITIVE,REFERENCE_NEGATIVE,action_rig
    reference=Path(reference); checksum=digest(reference)
    folder=DATA/'characters'/('side_'+checksum[:12]); folder.mkdir(parents=True,exist_ok=True)
    target=folder/'reference.png'
    if target.exists() and digest(target)!=checksum:
        raise ValueError('该参考版本的文件已被修改，拒绝覆盖；请使用新的角色版本。')
    if not target.exists(): shutil.copy2(reference,target)
    analysis=prepare_reference(target,client)
    base=json.loads(Path(analysis['rig']).read_text('utf-8'))
    server_ref=client.upload_image(analysis['opaque'])
    poses={}
    for key,label in [('stand','侧视站立 · 自动适配'),('reach','向前伸手 · 自动适配')]:
        rig=action_rig(base,key); write_json(folder/(key+'.json'),rig)
        image=folder/(key+'.png'); paint_pose(rig).save(str(image))
        overlay=folder/(key+'_overlay.png'); paint_pose(rig,analysis['rgba']).save(str(overlay))
        graph=character_workflow(server_ref,client.upload_image(image))
        graph['2']['inputs']['text']=REFERENCE_POSITIVE+', body pose matching the OpenPose map'
        graph['3']['inputs']['text']=REFERENCE_NEGATIVE
        path=folder/(key+'_api.json'); write_json(path,graph)
        poses[key]={'title':label,'graph':str(path),'image':str(image),'overlay':str(overlay),'rig':str(folder/(key+'.json'))}
    baseline=character_workflow(server_ref)
    baseline['2']['inputs']['text']=REFERENCE_POSITIVE
    baseline['3']['inputs']['text']=REFERENCE_NEGATIVE
    write_json(folder/'baseline_api.json',baseline)
    profile={'schema_version':2,'id':folder.name,'title':title,'reference':str(target),'source_sha256':checksum,
        'width':768,'height':1024,'positive':REFERENCE_POSITIVE,'pose_positive':REFERENCE_POSITIVE+', body pose matching the OpenPose map',
        'negative':REFERENCE_NEGATIVE,'baseline_graph':str(folder/'baseline_api.json'),'poses':poses,'adaptive':True,
        'analysis':analysis,'default_denoise':.3,'pose_requires':'controlnet-openpose-sdxl-1.0-xinsir.safetensors'}
    path=folder/'profile.json'; write_json(path,profile); write_json(ACTIVE_PROFILE_FILE,{'profile':str(path)})
    write_json(DATA/'chat'/'active-workflow.json',{'graph':baseline,'title':title,'character_id':profile['id'],'route':'baseline'})
    return profile
