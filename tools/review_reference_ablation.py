"""Compose labelled PNG evidence without modifying any experiment output."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps


def sheet(items, target, columns=3, cell=(400, 500)):
    rows=(len(items)+columns-1)//columns
    canvas=Image.new('RGB',(columns*cell[0],rows*cell[1]),'#e7e7e7')
    draw=ImageDraw.Draw(canvas)
    for index,(label,path) in enumerate(items):
        left=index%columns*cell[0];top=index//columns*cell[1]
        draw.text((left+8,top+7),label,fill='black')
        if path is None:
            draw.text((left+8,top+35),'Not completed',fill='black');continue
        with Image.open(path) as opened:
            picture=ImageOps.contain(opened.convert('RGB'),(cell[0]-8,cell[1]-30))
        canvas.paste(picture,(left+(cell[0]-picture.width)//2,top+26+(cell[1]-30-picture.height)//2))
    canvas.save(target)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof',type=Path,required=True);args=parser.parse_args()
    plan=json.loads((args.proof/'plan.json').read_text('utf-8'))
    for case in plan['cases']:
        folder=args.proof/case['name'];folder.mkdir(exist_ok=True)
        items=[]
        for offset in range(3):
            for mode in ('auto','no_caption','short'):
                saved=folder/f'{mode}_s{offset}'/'trial.json'
                record=json.loads(saved.read_text('utf-8')) if saved.is_file() else {}
                items.append((f'{mode} / seed +{offset}',record.get('result',[None])[0]))
        sheet(items,folder/'primary-comparison.png')
        items=[]
        for label,tag in [('auto','auto_s0'),('trigger only','trigger_only_s0'),('empty','empty_s0'),('short','short_s0'),('Base 20/5 short','base_short_s0')]:
            saved=folder/tag/'trial.json';record=json.loads(saved.read_text('utf-8')) if saved.is_file() else {}
            items.append((label,record.get('result',[None])[0]))
        sheet(items,folder/'exploratory-comparison.png')
        sheet([(key,entry['path']) for key,entry in case['images'].items()],folder/'inputs.png',columns=2)
    print('Labelled PNG evidence saved; visual quality still requires review.')


if __name__=='__main__':main()
