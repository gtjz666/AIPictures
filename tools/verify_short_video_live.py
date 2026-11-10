"""One serial real storyboard/AV run. Existing completed stages are reused, never rerolled."""
import argparse
import json
import threading
from pathlib import Path
import av
import numpy as np
from PIL import Image,ImageDraw
from aipictures.storage import write_json
from aipictures import video_script
from aipictures.h3_backend import settings as h3_settings
from aipictures.local_intent import settings as intent_settings
from aipictures.motion_native_backend import release_shared
from aipictures.video_generation import generate
from aipictures.video_audio import separate,read_audio


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reuse-script',type=Path,help='Reuse a reviewed script after an inspected interrupted run; do not rerun the assistant.')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    cancel=threading.Event()
    def emit(kind,value):
        if kind in ('video_stage','intent_stage','progress','video_decode_progress'):
            row=dict(kind=kind,data=value)
            with (out/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            print(json.dumps(row,ensure_ascii=False),flush=True)
    # Respect the user's existing enabled setting; no new background startup policy.
    setting=args.data/'gpu-watch-settings.json'
    if setting.is_file() and json.loads(setting.read_text('utf-8')).get('enabled'):
        from aipictures.gpu_watch import start
        start(args.data)
    if args.reuse_script and not (out/'script').exists():
        from aipictures.workflow_library import digest
        script=json.loads(args.reuse_script.read_text('utf-8'));video_script.validate(script,2)
        script['negative_prompt']=script.get('negative_prompt','').strip() or video_script.QUALITY_NEGATIVE
        (out/'script').mkdir();video_script.write_script(out/'script',script)
        write_json(out/'script/reused.json',dict(source=str(args.reuse_script.resolve()),sha256=digest(args.reuse_script),
            note='Reused the completed real assistant result; empty quality negatives normalized locally, no extra model request.'))
    if (out/'script/script.json').is_file():
        script=json.loads((out/'script/script.json').read_text('utf-8'));video_script.validate(script,2)
    else:
        if (out/'script').exists():raise ValueError('脚本任务已有未完成记录，请检查；不自动重跑。')
        config=intent_settings(args.data)
        if not config:raise ValueError('缺少已验证本地创作助手。')
        release_shared({},folder=out,cancel=cancel)
        script=video_script.organize(config,'清晨湖面，一艘红色小木船缓慢前行。镜头轻轻向前推进，水面有细小波纹。只要水声，不要对白和字幕，配舒缓旋律。',
            2,'gentle',None,out/'script',cancel,emit)
    folder=out/'generation'
    if (folder/'video.json').is_file() and json.loads((folder/'video.json').read_text('utf-8'))['status']=='completed':
        result=dict(manifest=str(folder/'video.json'))
    else:
        if folder.exists():raise ValueError('视频任务已有未完成记录，请检查；不自动重新生成。')
        folder.mkdir();config=h3_settings(args.data)
        if not config:raise ValueError('缺少已验证H3环境。')
        params=dict(engine='h3',h3_settings=config,prompt=video_script.prompt(script),negative=script['negative_prompt'],
            creation_kind='short_video',short_script=script,music_style='gentle',music_file=None,
            prompt_layout='unified',defer_exports=True,reference=None,seconds=2,seed=20261110,url=None)
        write_json(folder/'job.json',dict(kind='video',status='running',params=params));video_script.write_script(folder,script)
        try:
            result=generate(None,folder,params,cancel,emit)
            write_json(folder/'job.json',dict(kind='video',status='completed',params=params))
        except BaseException as exc:
            cancel.set();write_json(folder/'job.json',dict(kind='video',status='failed',error=str(exc),params=params));raise
    manifest=json.loads(Path(result['manifest']).read_text('utf-8'));source=Path(manifest['source_video'])
    separated=out/'separated';separated.mkdir(exist_ok=True)
    separate(source,separated/'video.mp4',separated/'soundtrack.wav',cancel)
    with av.open(str(source)) as c:
        info=dict(video_codec=c.streams.video[0].codec_context.name,audio_codec=c.streams.audio[0].codec_context.name,
                  audio_rate=c.streams.audio[0].sample_rate,streams=len(c.streams))
        rgb=np.stack([frame.to_ndarray(format='rgb24') for frame in c.decode(video=0)])
    native=np.load(manifest['native_rgb_source'],mmap_mode='r')
    assert np.array_equal(rgb,native[:len(rgb)])
    with av.open(str(separated/'video.mp4')) as c:
        assert not c.streams.audio
        for index,frame in enumerate(c.decode(video=0)):assert np.array_equal(frame.to_ndarray(format='rgb24'),rgb[index])
    sound=read_audio(separated/'soundtrack.wav',manifest['duration_seconds'])
    rms=float(np.sqrt(np.mean(sound**2)));assert rms>.001
    contact=Image.new('RGB',(384*4,512),'white')
    for j,index in enumerate(np.linspace(0,len(rgb)-1,4).astype(int)):
        frame=Image.fromarray(rgb[index]);frame.thumbnail((384,492));contact.paste(frame,(j*384,0))
        ImageDraw.Draw(contact).text((j*384+4,496),f'{index/24:.2f}s',fill='black')
    contact.save(out/'contact.png')
    write_json(out/'acceptance.json',dict(real_models=True,seconds=manifest['duration_seconds'],frame_count=len(rgb),
        exact_rgb_preserved=True,separation_pixels_equal=True,soundtrack_rms=rms,native_audio=manifest['native_audio_present'],
        music_source=manifest['music_source'],media=info,manifest=str(result['manifest'])))
    print('Real storyboard / H3 / original music / AV separation: PASS',flush=True)


if __name__=='__main__':main()
