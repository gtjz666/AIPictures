"""Make evidence sheets from actual raw frames, without sharpening or recoloring."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image,ImageDraw,ImageFont
from aipictures.storage import write_json


def review(baseline:Path,trials:list[Path],out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    groups=[('Baseline 480 -> 768',json.loads(baseline.read_text('utf-8')))]
    for trial in trials:
        if not (trial/'video/result.json').is_file():
            raise ValueError(str(trial)+' 尚未保存完整结果，请等待生成或恢复解码后再制作对照。')
        groups.append((trial.name,json.loads((trial/'video/result.json').read_text('utf-8'))))
    count=len(groups[0][1]['images'])
    if any(len(result['images'])!=count for _,result in groups):
        raise ValueError('对照的原始帧数不一致。')
    indices=sorted(set((0,count//2,max(0,count-3))))
    font_path=Path('C:/Windows/Fonts/msyh.ttc')
    font=ImageFont.truetype(str(font_path),17) if font_path.is_file() else ImageFont.load_default()
    sheet=Image.new('RGB',(384*len(groups),len(indices)*540),'#eeeeee');draw=ImageDraw.Draw(sheet)
    # Identical canvas-coordinate crops, shown at 100% pixels. The baseline is
    # enlarged using its existing export interpolation; native frames are not.
    regions=[('head',(260,65,535,330)),('arm',(240,350,510,650)),('feet',(240,810,640,1010))]
    detail=Image.new('RGB',(400*len(groups),sum(330 for _ in regions)),'#eeeeee');dd=ImageDraw.Draw(detail)
    records=[]
    for column,(title,result) in enumerate(groups):
        sizes=[];hashes=[]
        for path in result['images']:
            with Image.open(path) as image:
                sizes.append(list(image.size));hashes.append(hashlib.sha256(image.convert('RGB').tobytes()).hexdigest())
        if len({tuple(s) for s in sizes})!=1:raise ValueError(title+' 组内帧尺寸不同。')
        records.append({'title':title,'prompt_id':result['prompt_id'],'raw_frame_count':count,
            'native_size':sizes[0],'unique_raw_frame_hashes':len(set(hashes)),
            'pixel_hashes':hashes,'enlarged_for_comparison':sizes[0]!=[768,1024]})
        for row,index in enumerate(indices):
            with Image.open(result['images'][index]) as image:
                image=image.convert('RGB')
                if image.size!=(768,1024):image=image.resize((768,1024),Image.Resampling.LANCZOS)
                thumbnail=image.resize((384,512),Image.Resampling.LANCZOS)
                sheet.paste(thumbnail,(column*384,row*540+28))
            draw.text((column*384+5,row*540+4),f'{title} / frame {index}',font=font,fill='black')
        with Image.open(result['images'][0]) as image:
            image=image.convert('RGB')
            if image.size!=(768,1024):image=image.resize((768,1024),Image.Resampling.LANCZOS)
            for row,(name,box) in enumerate(regions):
                crop=image.crop(box)
                detail.paste(crop,(column*400+(400-crop.width)//2,row*330+28))
                dd.text((column*400+5,row*330+4),f'{title} / {name} / 100%',font=font,fill='black')
    sheet.save(out/'comparison.png');detail.save(out/'detail_100_percent.png')
    report={'status':'completed','comparison_indices':indices,'groups':records,
        'processing':'Only documented display resizing of raw frames; no sharpening, AI restoration, palette changes or temporal mixing.',
        'crop_canvas':[768,1024],'crop_regions':regions,
        'warnings':['像素数量与唯一帧数不能证明人体结构、角色一致性或通用准确率；必须人工检查整段动画。']}
    write_json(out/'report.json',report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--trial',type=Path,action='append',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report=review(a.baseline,a.trial,a.out)
    print(json.dumps({'status':report['status'],'groups':len(report['groups']),'report':str(a.out/'report.json')},ensure_ascii=False))


if __name__=='__main__':main()
