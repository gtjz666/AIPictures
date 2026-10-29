"""Analyze each imported full-body side-view reference once, then reuse its own colors/rig."""
import json
import math
import threading
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image,ImageOps,ImageFilter
from scipy import ndimage

from .background import foreground_rgba
from .character_profile import JOINT_NAMES,rig_document,paint_pose
from .engine import Cancelled
from .storage import DATA,write_json
from .workflow_library import digest

SIZE=(768,1024)
ANALYSIS_VERSION=3
REFERENCE_POSITIVE=('one single full-body 2D illustrated character, same character as the supplied reference image, '
    'strict side profile, preserve the exact hair color, hairstyle, clothing colors, footwear and body proportions '
    'from the reference, clean outlines, consistent flat colors, fixed camera and framing, plain background')
REFERENCE_NEGATIVE=('different character, changed hairstyle, changed outfit, changed colors, faded colors, '
    'transparent body parts, missing texture, extra arms, extra legs, extra fingers, missing limbs, '
    'deformed anatomy, front view, cropped head, cropped feet, multiple people, text, watermark, blurry')


class PoseNotApplicable(ValueError):
    """The image may be a valid reference without being an OpenPose-compatible person."""


def clean_foreground(image,repair_interior=True):
    """Ignore isolated near-transparent specks without cutting holes into colored clothing."""
    rgba=np.array(image.convert('RGBA'))
    labels,count=ndimage.label(rgba[:,:,3]>24)
    if not count: raise ValueError('图片没有可识别的主体，请换一张清晰的参考图。')
    sizes=np.bincount(labels.ravel()); sizes[0]=0; main=labels==int(sizes.argmax())
    if int(main.sum())<200: raise ValueError('参考主体太小，请使用更清晰的图片。')
    nearby=ndimage.binary_dilation(main,iterations=2)
    rgba[:,:,3]=np.where(nearby,rgba[:,:,3],0)
    # Tiny matte pinholes inside a solid region are repaired using neighboring source colors.
    holes=ndimage.binary_fill_holes(main)&~main if repair_interior else np.zeros_like(main)
    hole_labels,hole_count=ndimage.label(holes)
    if hole_count:
        hole_sizes=np.bincount(hole_labels.ravel())
        tiny=(hole_labels>0)&(hole_sizes[hole_labels]<=max(4,int(main.sum()*.00015)))
        if tiny.any():
            indices=ndimage.distance_transform_edt(~main,return_distances=False,return_indices=True)
            rgba[tiny,:3]=rgba[indices[0][tiny],indices[1][tiny],:3]
            rgba[tiny,3]=255
    if repair_interior:
        inside=ndimage.distance_transform_edt(main)>2
        rgba[inside,3]=255
    return Image.fromarray(rgba)


def normalize_reference(image):
    image=clean_foreground(image)
    binary=image.getchannel('A').point(lambda a:255 if a>24 else 0)
    box=binary.getbbox(); crop=image.crop(box)
    scale=min(900/crop.height,380/crop.width)
    new_size=(max(1,round(crop.width*scale)),max(1,round(crop.height*scale)))
    subject=crop.resize(new_size,Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',SIZE)
    xy=(round(384-new_size[0]/2),978-new_size[1]); canvas.paste(subject,xy)
    return canvas,{'source_bbox':list(box),'scale':scale,'offset':list(xy),'subject_bbox':[xy[0],xy[1],xy[0]+new_size[0],978]}


def opaque_reference(rgba):
    image=Image.new('RGB',rgba.size,(242,243,245))
    image.paste(rgba,mask=rgba.getchannel('A')); return image


def detection_workflow(image):
    return {'1':{'class_type':'LoadImage','inputs':{'image':image}},
        '2':{'class_type':'DWPreprocessor','inputs':{'image':['1',0],'detect_body':'enable','detect_hand':'enable',
            'detect_face':'disable','resolution':768,'bbox_detector':'None','pose_estimator':'dw-ll_ucoco_384.onnx',
            'scale_stick_for_xinsr_cn':'disable'}},
        '3':{'class_type':'SaveImage','inputs':{'images':['2',0],'filename_prefix':'AIPictures/reference_analysis'}}}


def parse_detected_pose(history):
    for output in history.get('outputs',{}).values():
        if output.get('openpose_json'):
            frames=json.loads(output['openpose_json'][0])
            frame=frames[0] if isinstance(frames,list) else frames
            people=frame.get('people',[])
            if len(people)!=1: raise PoseNotApplicable('未识别到唯一完整的人体姿态。')
            coordinates=people[0]['pose_keypoints_2d']
            return frame,np.asarray(coordinates[:54],dtype=np.float64).reshape(18,3)
    raise PoseNotApplicable('姿态识别没有返回可用的人体关节坐标。')


def aligned_rig(points,canvas,rgba,hands=None):
    """Use measured visible joints; explicitly estimate occluded counterparts."""
    points=points.copy(); points[:,0]*=768/canvas[0]; points[:,1]*=1024/canvas[1]
    required=(0,1,2,3,4,5,6,7,8,9,10,11,12,13)
    visible=[i for i in required if points[i,2]>.25]
    if len(visible)<10: raise PoseNotApplicable('人体关节识别不完整；卡通角色可使用 AI 连续动画。')
    direction='right' if points[0,0]>=points[1,0] else 'left'
    if direction=='left':
        rgba=ImageOps.mirror(rgba); points[:,0]=767-points[:,0]
    arm_sides=[(2,3,4),(5,6,7)]
    arm=min(arm_sides,key=lambda ids:float(points[list(ids),0].mean()))
    leg=(8,9,10) if arm[0]==2 else (11,12,13)
    for index in (*arm,*leg):
        if points[index,2]<.25: raise PoseNotApplicable('可见侧的手臂或腿未识别完整。')
    hand=None
    if hands:
        hand=hands.get('right' if arm[0]==2 else 'left')
        if hand is not None:
            hand=hand.copy()
            if direction=='left': hand[:,0]=767-hand[:,0]
            if int((hand[:,2]>.25).sum())<10: hand=None
            elif math.dist(hand[0,:2],points[arm[2],:2])<45: points[arm[2],:2]=hand[0,:2]
    canonical=points.copy()
    for target,source in zip((2,3,4,8,9,10),(*arm,*leg)): canonical[target]=points[source]
    body_width=rgba.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()[2]-rgba.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()[0]
    for near,far in ((2,5),(3,6),(4,7),(8,11),(9,12),(10,13)):
        canonical[far]=canonical[near]+np.array([max(5,body_width*.07),0,0]); canonical[far,2]=.35
    lengths=[math.dist(canonical[a,:2],canonical[b,:2]) for a,b in ((2,3),(3,4),(8,9),(9,10))]
    if min(lengths)<35 or max(lengths)>400:
        raise PoseNotApplicable('检测到的角色比例不适合人体骨骼。')
    # A front-facing person has a broad shoulder axis; this release is a profile walk.
    shoulder_gap=abs(points[2,0]-points[5,0])
    if shoulder_gap>max(75,body_width*.6): raise PoseNotApplicable('当前人体骨骼适配器面向侧视人物。')
    rig=rig_document(); rig.update(schema_version=4,rig_id='detected_side_v2',annotation='dwpose_visible_with_occluded_estimates',
        source_direction=direction,ground_y=978,
        notes='DWPose 识别可见侧；遮挡侧按可见侧估计。未识别的面部点不用于肢体分层。')
    rig['joints']={name:canonical[i].tolist() for i,name in enumerate(JOINT_NAMES)}
    if hand is not None: rig['visible_hand_keypoints']=hand.tolist()
    return rig,rgba


def prepare_reference(reference,client,emit=lambda *_:None,cancel=None):
    cancel=cancel or threading.Event(); reference=Path(reference)
    key=digest(reference); folder=DATA/'reference-analysis'/f'v{ANALYSIS_VERSION}_{key[:20]}'
    manifest=folder/'analysis.json'
    if manifest.exists():
        result=json.loads(manifest.read_text('utf-8'))
        if all(Path(result[name]).is_file() for name in ('rgba','opaque','rig')): return result
    if cancel.is_set(): raise Cancelled('参考图分析已取消')
    folder.mkdir(parents=True,exist_ok=True); emit('reference_stage',{'message':'识别参考图主体与透明区域…'})
    with Image.open(reference) as original:
        source=foreground_rgba(ImageOps.exif_transpose(original),cancel)
    normalized,geometry=normalize_reference(source)
    normalized.save(folder/'reference_rgba.png'); opaque_reference(normalized).save(folder/'reference_rgb.png')
    # Tight crop helps detect the narrow silhouette; map returned coordinates back to the canvas.
    box=normalized.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()
    crop_box=(max(0,box[0]-25),0,min(768,box[2]+25),1024)
    opaque_reference(normalized).crop(crop_box).save(folder/'detection_input.png')
    emit('reference_stage',{'message':'DWPose 识别可见关节，适配人物比例…'})
    detection=folder/'detection'; detection.mkdir(exist_ok=True)
    name=client.upload_image(folder/'detection_input.png')
    graph=detection_workflow(name); write_json(detection/'workflow.json',graph)
    result=client.generate(graph,detection,lambda k,d:emit('reference_event',{'event':k,'data':d}),cancel)
    write_json(detection/'result.json',result)
    frame,points=parse_detected_pose(result['history'])
    points[:,0]=points[:,0]*(crop_box[2]-crop_box[0])/frame['canvas_width']+crop_box[0]
    points[:,1]*=1024/frame['canvas_height']
    hands={}
    for side in ('left','right'):
        values=frame['people'][0].get('hand_'+side+'_keypoints_2d')
        if values:
            hand=np.asarray(values,dtype=float).reshape(-1,3)
            hand[:,0]=hand[:,0]*(crop_box[2]-crop_box[0])/frame['canvas_width']+crop_box[0]
            hand[:,1]*=1024/frame['canvas_height']; hands[side]=hand
    rig,normalized=aligned_rig(points,SIZE,normalized,hands)
    normalized.save(folder/'reference_rgba.png'); opaque_reference(normalized).save(folder/'reference_rgb.png')
    write_json(folder/'rig.json',rig); paint_pose(rig).save(str(folder/'pose.png'))
    metadata={'schema_version':2,'source':str(reference),'source_sha256':key,'rig':str(folder/'rig.json'),
        'rgba':str(folder/'reference_rgba.png'),'opaque':str(folder/'reference_rgb.png'),
        'pose_image':str(folder/'pose.png'),'geometry':geometry,'direction':rig['source_direction'],
        'detector_prompt_id':result['prompt_id'],'color_policy':'source_rgb_preserved_straight_alpha'}
    if cancel.is_set(): raise Cancelled('参考图分析已取消')
    write_json(manifest,metadata); return metadata


def action_rig(base,action):
    if action=='walk':
        from .walk_cycle import walk_rig
        return walk_rig(0,base_rig=base)
    rig=deepcopy(base)
    if action=='reach':
        joints=rig['joints']; shoulder=joints['right_shoulder']
        upper=math.dist(shoulder[:2],joints['right_elbow'][:2]); lower=math.dist(joints['right_elbow'][:2],joints['right_wrist'][:2])
        elbow=[shoulder[0]+upper*.78,shoulder[1]+upper*.626,1]
        joints['right_elbow']=elbow; joints['right_wrist']=[elbow[0]+lower*.98,elbow[1]-lower*.199,1]
    return rig
