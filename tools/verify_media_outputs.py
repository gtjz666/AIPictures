"""Stream-check complete real AV output and independent music without loading models."""
import argparse
import json
import threading
from pathlib import Path
import av
import numpy as np
from PIL import Image,ImageDraw
from aipictures.storage import write_json
from aipictures.video_audio import read_audio,separate


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--video',type=Path,required=True);parser.add_argument('--audio',type=Path)
    parser.add_argument('--proof',type=Path,required=True);parser.add_argument('--minimum-seconds',type=float,default=30)
    args=parser.parse_args();proof=args.proof;proof.mkdir(parents=True,exist_ok=True)
    data=json.loads(args.video.read_text('utf-8'));assert data['status']=='completed'
    source=Path(data['source_video']);count=data['frame_count'];fps=data['fps']
    native=np.load(data['native_rgb_source'],mmap_mode='r') if data.get('native_rgb_source') else None
    paths=[args.video.parent/row['image'] for row in data.get('frames',[])]
    indices=set(np.linspace(0,count-1,12).astype(int));pictures=[];decoded=0
    with av.open(str(source)) as container:
        assert len(container.streams.audio)==len(container.streams.video)==1
        rate=container.streams.audio[0].sample_rate
        for i,frame in enumerate(container.decode(video=0)):
            actual=frame.to_ndarray(format='rgb24')
            if native is not None:expected=native[i]
            else:
                with Image.open(paths[i]) as original:expected=np.asarray(original.convert('RGB'))
            assert np.array_equal(actual,expected),f'Pixel difference at {i}'
            if i in indices:pictures.append((i,Image.fromarray(actual)))
            decoded+=1
    assert decoded==count and count/fps>=args.minimum_seconds
    separate(source,proof/'picture-only.mp4',proof/'soundtrack.wav',threading.Event())
    with av.open(str(proof/'picture-only.mp4')) as container:
        assert not container.streams.audio;separated_count=0
        for i,frame in enumerate(container.decode(video=0)):
            if native is not None:expected=native[i]
            else:
                with Image.open(paths[i]) as original:expected=np.asarray(original.convert('RGB'))
            assert np.array_equal(frame.to_ndarray(format='rgb24'),expected),f'Separated pixel difference at {i}'
            separated_count+=1
    assert separated_count==count
    if native is not None:native._mmap.close()
    sound=read_audio(proof/'soundtrack.wav',count/fps);assert float(np.sqrt(np.mean(sound**2)))>.0001
    sheet=Image.new('RGB',(1024,384*3),'white')
    for slot,(index,picture) in enumerate(pictures):
        picture.thumbnail((256,360));x=(slot%4)*256;y=(slot//4)*384;sheet.paste(picture,(x,y))
        ImageDraw.Draw(sheet).text((x+4,y+363),f'{index/fps:.2f}s',fill='black')
    sheet.save(proof/'contact.png')
    result=dict(video=str(args.video.resolve()),frames=count,seconds=count/fps,exact_native_rgb=True,separated_frames=separated_count,
        audio_rate=rate,soundtrack_rms=float(np.sqrt(np.mean(sound**2))),separated_rgb_exact=True)
    if args.audio:
        music=json.loads(args.audio.read_text('utf-8'));assert music['status']=='completed'
        values=read_audio(music['audio'],music['duration_seconds'])
        assert values.shape[1]==round(music['duration_seconds']*48000) and float(np.sqrt(np.mean(values**2)))>.001
        result['standalone_audio']=dict(manifest=str(args.audio.resolve()),seconds=music['duration_seconds'],rms=float(np.sqrt(np.mean(values**2))),worker=music['worker'])
    write_json(proof/'acceptance.json',result);print('Real media streams / exact frames / AV separation / standalone audio: PASS')


if __name__=='__main__':main()
