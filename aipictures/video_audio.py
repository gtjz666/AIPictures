"""Separate original soundtrack, original local score, mix, and lossless video mux."""
from pathlib import Path
import math
import wave
import av
import numpy as np
from .engine import Cancelled

RATE=48000


def save_wav(path, samples, rate=RATE):
    samples=np.asarray(samples,dtype=np.float32)
    if samples.ndim!=2 or samples.shape[0]!=2 or not np.isfinite(samples).all():raise ValueError('音频数据无效。')
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate)
        f.writeframes((np.clip(samples.T,-1,1)*32767).round().astype('<i2').tobytes())


def read_audio(path, seconds, *, loop=False, cancel=None):
    count=round(seconds*RATE);blocks=[];size=0
    with av.open(str(path)) as source:
        if not source.streams.audio:raise ValueError('素材中没有音频轨。')
        resampler=av.AudioResampler(format='fltp',layout='stereo',rate=RATE)
        for frame in source.decode(audio=0):
            if cancel is not None and cancel.is_set():raise Cancelled('音频处理已取消。')
            for converted in resampler.resample(frame):
                block=converted.to_ndarray();blocks.append(block);size+=block.shape[1]
            if size>=count:break
        for converted in resampler.resample(None):blocks.append(converted.to_ndarray())
    if not blocks:raise ValueError('音频轨为空。')
    values=np.concatenate(blocks,axis=1)
    if not np.isfinite(values).all():raise ValueError('音频包含无效采样。')
    if values.shape[1]<count:
        if loop:values=np.tile(values,(1,math.ceil(count/values.shape[1])))
        else:values=np.pad(values,((0,0),(0,count-values.shape[1])))
    return np.ascontiguousarray(values[:,:count],dtype=np.float32)


def compose_music(seconds, style, seed):
    """Original small instrumental score, no GPU/model or third-party recordings."""
    if style not in ('gentle','bright','dramatic'):raise ValueError('未知自动配乐类型。')
    count=round(seconds*RATE);audio=np.zeros((2,count),np.float32)
    rng=np.random.default_rng(seed%(2**32));bpm={'gentle':84,'bright':112,'dramatic':96}[style]
    beat=60/bpm;root=57 if style=='dramatic' else 60
    chords=[(0,3,7),(5,8,12),(3,7,10),(7,10,14)] if style=='dramatic' else [(0,4,7),(5,9,12),(9,12,16),(7,11,14)]
    def note(start,duration,midi,gain,pan=0):
        a=round(start*RATE);n=min(round(duration*RATE),count-a)
        if n<=0:return
        t=np.arange(n)/RATE;freq=440*2**((midi-69)/12)
        signal=sum((1/h**1.5)*np.sin(2*np.pi*freq*h*t)*np.exp(-t*(1.8+h*.35)) for h in (1,2,3,5))
        signal*=np.minimum(t/.012,1)*np.minimum((n/RATE-t)/.06,1)*gain
        audio[0,a:a+n]+=signal*(1-pan*.35);audio[1,a:a+n]+=signal*(1+pan*.35)
    for i in range(math.ceil(seconds/beat)):
        chord=chords[(i//4)%len(chords)]
        note(i*beat,beat*1.8,root+chord[0]-12,.12)
        for j,key in enumerate(chord):note(i*beat,beat*1.9,root+key,.035,(j-1)*.6)
        melody=(0,2,1,2,0,1,2,1)[i%8]
        note(i*beat,beat*1.5,root+chord[melody]+12,.11,(-1)**i*.35)
        if style!='gentle':
            a=round((i+.5)*beat*RATE);n=min(round(.04*RATE),max(0,count-a))
            if n:
                hit=rng.standard_normal(n)*np.exp(-np.arange(n)/(RATE*.008))*.018
                audio[:,a:a+n]+=hit
    fade=min(round(.18*RATE),count//2)
    audio[:,:fade]*=np.linspace(0,1,fade);audio[:,-fade:]*=np.linspace(1,0,fade)
    peak=float(np.max(np.abs(audio)))
    if peak>0:audio*=.7/peak
    return audio


def mux(video, audio, target, cancel):
    """Copy video packets without another image encode; encode one AAC soundtrack."""
    temporary=Path(target).with_name(Path(target).stem+'.part.mp4')
    try:
        with av.open(str(video)) as src,av.open(str(temporary),'w') as dst:
            vin=src.streams.video[0];vout=dst.add_stream_from_template(vin,opaque=True)
            sound=dst.add_stream('aac',rate=RATE);sound.layout='stereo';sound.bit_rate=192000
            for packet in src.demux(vin):
                if cancel.is_set():raise Cancelled('音画合成已取消。')
                if packet.dts is not None:packet.stream=vout;dst.mux(packet)
            for start in range(0,audio.shape[1],1024):
                if cancel.is_set():raise Cancelled('音画合成已取消。')
                frame=av.AudioFrame.from_ndarray(audio[:,start:start+1024].copy(),format='fltp',layout='stereo')
                frame.sample_rate=RATE;frame.pts=start
                from fractions import Fraction
                frame.time_base=Fraction(1,RATE)
                for packet in sound.encode(frame):dst.mux(packet)
            for packet in sound.encode():dst.mux(packet)
        if cancel.is_set():raise Cancelled('音画合成已取消。')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def separate(source, silent, soundtrack, cancel):
    """Export independent picture stream and PCM WAV from any supported AV clip."""
    picture=Path(silent).with_name(Path(silent).stem+'.part.mp4')
    audio=Path(soundtrack).with_name(Path(soundtrack).stem+'.part.wav')
    try:
        with av.open(str(source)) as src:
            if not src.streams.video:raise ValueError('素材中没有视频轨。')
            stream=src.streams.video[0]
            duration=float(stream.duration*stream.time_base) if stream.duration else src.duration/av.time_base
            if not src.streams.audio:raise ValueError('素材中没有可分离音轨。')
            with av.open(str(picture),'w') as dst:
                out=dst.add_stream_from_template(stream,opaque=True)
                for packet in src.demux(stream):
                    if cancel.is_set():raise Cancelled('音画分离已取消。')
                    if packet.dts is not None:packet.stream=out;dst.mux(packet)
        save_wav(audio,read_audio(source,duration,cancel=cancel))
        if cancel.is_set():raise Cancelled('音画分离已取消。')
        picture.replace(silent);audio.replace(soundtrack)
    finally:
        picture.unlink(missing_ok=True);audio.unlink(missing_ok=True)


def package(folder, video, seconds, params, cancel):
    folder=Path(folder);rate=RATE;count=round(seconds*rate)
    native_path=folder/'native_audio.wav';native=np.zeros((2,count),np.float32);present=False
    array=folder/'animation.artifacts/audio.npy'
    if array.is_file():
        original=np.load(array,allow_pickle=False)
        if original.ndim!=2 or original.shape[0]!=2 or not np.isfinite(original).all():raise ValueError('原生音轨数据无效。')
        original=original[:,:round(seconds*32000)];save_wav(native_path,original,32000)
        native=read_audio(native_path,seconds,cancel=cancel);present=True
    elif video and Path(video).is_file():
        with av.open(str(video)) as c:present=bool(c.streams.audio)
        if present:native=read_audio(video,seconds,cancel=cancel);save_wav(native_path,native)
    imported=params.get('music_file')
    if params.get('audio_mode')=='h3_native' and not imported:
        if not present:raise ValueError('此路线没有生成原生音轨，不能交付带声成片；画面和日志已保留。')
        if float(np.sqrt(np.mean(native**2)))<.0001:raise ValueError('H3原生音轨接近静音，请检查本次生成；不会用合成旋律替代。')
        save_wav(folder/'soundtrack.wav',native)
        silent=folder/'video_silent.mp4';target=folder/'video_with_audio.mp4'
        mux(silent,native,target,cancel)
        return dict(video=str(target.resolve()),silent_video=str(silent.resolve()),audio=str((folder/'soundtrack.wav').resolve()),
            music=None,native_audio=str(native_path.resolve()),music_source='h3_native',native_audio_present=True,sample_rate=rate,duration_seconds=seconds)
    music=read_audio(imported,seconds,loop=True,cancel=cancel) if imported else compose_music(seconds,params.get('music_style','gentle'),params['seed'])
    mix=native*.8+music*(.35 if present else .85)
    peak=float(np.max(np.abs(mix)))
    if peak>.98:mix*=.98/peak
    if float(np.sqrt(np.mean(music**2)))<.0001:raise ValueError('配乐音量过低，请更换配乐素材。')
    save_wav(folder/'music.wav',music);save_wav(folder/'soundtrack.wav',mix)
    silent=folder/'video_silent.mp4';target=folder/'video_with_audio.mp4'
    if not silent.is_file():raise ValueError('完整无声画面尚未保存，无法配乐。')
    mux(silent,mix,target,cancel)
    with av.open(str(target)) as c:
        if len(c.streams.audio)!=1 or len(c.streams.video)!=1:raise ValueError('音画合成结果不完整。')
    return dict(video=str(target.resolve()),silent_video=str(silent.resolve()),audio=str((folder/'soundtrack.wav').resolve()),
                music=str((folder/'music.wav').resolve()),native_audio=str(native_path.resolve()) if present else None,
                music_source='imported' if imported else 'original_local_score',native_audio_present=present,
                sample_rate=rate,duration_seconds=seconds)
