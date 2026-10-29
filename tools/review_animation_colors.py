"""Review corrections on completed transparent frames in a separate folder, no GPU job."""
import argparse
import json
import time
import shutil
from copy import deepcopy
from pathlib import Path
from datetime import datetime
from PIL import Image,ImageDraw,ImageOps
from aipictures.storage import DATA,write_json
from aipictures.palette_consistency import palette_plan,apply_palette
from aipictures.hand_quality import repair_reference_hands
from aipictures.foot_quality import repair_light_footwear
from aipictures.reference_color import repair_reference_hair
from aipictures.walk_cycle import export_sequence


def review(folder):
    folder=Path(folder).resolve(); manifest=json.loads((folder/'sequence.json').read_text('utf-8'))
    if manifest['status']!='completed': raise ValueError('只检查已完成任务。')
    clip=json.loads((folder/'motion.json').read_text('utf-8'))
    analysis=json.loads((folder/'reference_analysis.json').read_text('utf-8'))
    reference=Image.open(analysis['rgba']).convert('RGBA'); base=deepcopy(clip['base_rig'])
    if manifest.get('source_direction')=='left':
        reference=ImageOps.mirror(reference)
        for p in base['joints'].values(): p[0]=767-p[0]
        for p in base.get('visible_hand_keypoints',[]): p[0]=767-p[0]
    paths=[]
    for item in manifest['frames']:
        matte=folder/f'frame_{item["index"]:03d}/matte.png'
        paths.append(matte if matte.is_file() and manifest.get('source_direction')!='left' else folder/item['image'])
    poses=[json.loads((folder/item['pose']).read_text('utf-8')) for item in manifest['frames']]
    output=DATA/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_palette_')+folder.name[-8:]); output.mkdir(parents=True)
    started=time.monotonic(); plan=palette_plan(paths,poses,reference,base); reports=[]; outputs=[]; comparisons=[]
    updated=deepcopy(manifest);updated['frames']=[]
    updated.update(title=manifest.get('title','动作动画')+' · 配色修订',reference_palette=plan,
        reprocessing={'source':str(folder),'new_inference':False,'originals_unchanged':True})
    for name in ('motion.json','reference_analysis.json'):shutil.copy2(folder/name,output/name)
    (output/'video').mkdir()
    if (folder/'video/workflow.json').is_file():shutil.copy2(folder/'video/workflow.json',output/'video/workflow.json')
    for i,(path,pose) in enumerate(zip(paths,poses)):
        with Image.open(path) as image: before=image.convert('RGBA')
        after,palette_report=apply_palette(before,pose,plan['frames'][i])
        after,hair_report=repair_reference_hair(after,reference,pose,base)
        after,hand_report=repair_reference_hands(after,reference,pose,base)
        after,foot_report=repair_light_footwear(after,reference,pose,base)
        report={'frame':i,'palette':palette_report,'hands':hand_report,'feet':foot_report,'hair':hair_report};reports.append(report)
        key=output/f'frame_{i:03d}';key.mkdir()
        before.save(key/'matte.png');write_json(key/'pose.json',pose);write_json(key/'palette-quality.json',palette_report)
        entry=deepcopy(manifest['frames'][i]);entry.update(reference_palette=palette_report,hand_quality=hand_report,
            foot_quality=foot_report,hair_quality=hair_report)
        updated['frames'].append(entry)
        target=output/f'frame_{i:03d}.png'; after.save(target); outputs.append(target)
        feet=[pose['joints'][side+'_ankle'] for side in ('left','right')]
        foot_box=(max(0,int(min(p[0] for p in feet))-85),max(0,int(min(p[1] for p in feet))-100),
            min(after.width,int(max(p[0] for p in feet))+100),min(after.height,int(max(p[1] for p in feet))+60))
        after.crop(foot_box).save(key/'feet.png')
        wrists=[pose['joints'][side+'_wrist'] for side in ('left','right')]
        box=(max(0,int(min(p[0] for p in wrists))-75),max(0,int(min(p[1] for p in wrists))-50),
             min(768,int(max(p[0] for p in wrists))+95),min(1024,int(max(p[1] for p in wrists))+100))
        pair=Image.new('RGB',(600,220),'#eeeeee')
        for j,image in enumerate((before,after)):
            crop=image.crop(box); crop.thumbnail((290,190),Image.Resampling.LANCZOS)
            bg=Image.new('RGBA',crop.size,'#eeeeee'); bg.alpha_composite(crop); pair.paste(bg.convert('RGB'),(j*300,25))
            ImageDraw.Draw(pair).text((j*300+8,5),f'Frame {i+1} '+('before' if j==0 else 'after'),fill='black')
        comparisons.append(pair)
    sheet=Image.new('RGB',(1200,220*((len(comparisons)+1)//2)),'white')
    for i,pair in enumerate(comparisons): sheet.paste(pair,(i%2*600,i//2*220))
    sheet.save(output/'hands-before-after.jpg')
    exports=export_sequence(output,outputs,manifest['fps'],manifest['action'])
    from aipictures.pose_animation import build_foot_review
    build_foot_review(output,len(outputs))
    updated['exports']=exports;write_json(output/'sequence.json',updated)
    write_json(output/'reference-palette-plan.json',plan)
    write_json(output/'report.json',{'source':str(folder),'originals_unchanged':True,'new_inference':False,
        'seconds':round(time.monotonic()-started,3),'color':plan,'frames':reports,'exports':exports})
    print(json.dumps({'folder':str(output),'palette_changed_pixels':[item['palette']['changed_pixels'] for item in reports],
        'review':[item['palette']['requires_review'] for item in reports]},ensure_ascii=True),flush=True)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('folder'); review(parser.parse_args().folder)
