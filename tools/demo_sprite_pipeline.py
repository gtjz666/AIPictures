"""Small synthetic acceptance fixture, clearly separate from AI model output."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from sprite_pipeline import PipelineConfig, run_pipeline
from sprite_pipeline.config import write_document


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,default=Path('data/sprite-demo'))
    args=parser.parse_args(); source=args.out/'input'; source.mkdir(parents=True,exist_ok=True)
    for index,(dx,leg) in enumerate(((0,-2),(2,0),(-1,2))):
        image=Image.new('RGBA',(32,40)); draw=ImageDraw.Draw(image)
        draw.rectangle((12+dx,5,19+dx,12),fill=(48+index,38,82,255))
        draw.rectangle((10+dx,13,21+dx,24),fill=(196+index*2,55,64,255))
        draw.rectangle((11+dx,25,14+dx,32+leg),fill=(40,48+index,72,255))
        draw.rectangle((17+dx,25,20+dx,32-leg),fill=(40,48+index,72,255))
        draw.rectangle((11+dx,8,16+dx,12),fill=(239,194+index,149,255))
        # Simulate AI enlarged, softened pixel art; only this fixture blurs.
        image=image.resize((128,160),Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(.45))
        image.save(source/f'frame_{[1,2,10][index]}.png')
        if index==0: image.save(args.out/'anchor.png')
    config=PipelineConfig(canvas_width=40,canvas_height=48,pixel_size=4,palette_size=8,
        anchor=str((args.out/'anchor.png').resolve()),seed=4242,padding=2,columns=3)
    write_document(args.out/'pipeline.json',config.document())
    report=run_pipeline(source,args.out/'out',config)
    with Image.open(args.out/'out/sprite_sheet.png') as sheet:
        sheet.resize((sheet.width*4,sheet.height*4),Image.Resampling.NEAREST).save(args.out/'nearest-preview.png')
    print('Synthetic demo (not AI-generated):',report['pass'],args.out.resolve())


if __name__=='__main__': main()
