"""Deliver real musical coverage, without looping, changing tempo or padding silence."""
import math
import wave
import numpy as np

RATE=48000


def render_seconds(seconds):
    return math.ceil(seconds+min(12,max(5,seconds*.25+4)))


def finish(path,seconds):
    with wave.open(str(path),'rb') as source:
        if source.getsampwidth()!=2 or source.getnchannels()!=2 or source.getframerate()!=RATE:
            raise ValueError('音乐原始输出格式不符，未补齐或伪造时长。')
        samples=np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').reshape(-1,2).T.astype(np.float32)/32768
    count=round(seconds*RATE)
    if samples.shape[1]<count:raise ValueError('模型原始音乐不足所选时长，原文件保留，未添加静音。')
    window=RATE//20
    energies=np.array([np.sqrt(np.mean(samples[:,i:i+window]**2)) for i in range(0,samples.shape[1],window)])
    threshold=max(.0016,float(np.percentile(energies,80))*.015)
    active=np.flatnonzero(energies>threshold)
    if not len(active):raise ValueError('生成结果没有足够的有效音乐。')
    first=int(active[0]*window);last=min(samples.shape[1],int((active[-1]+1)*window))
    # A short natural release is allowed; several seconds of floor noise are not.
    if last-first<count-round(.35*RATE):
        raise ValueError(f'有效音乐约{(last-first)/RATE:.1f}秒，不足所选{seconds:g}秒；原始文件已保留，未用循环或静音补足。')
    end=min(samples.shape[1],last+round(.2*RATE));start=end-count
    if start<0:raise ValueError('音乐时长不足，未补静音。')
    output=samples[:,start:end].copy()
    fade=min(round(.12*RATE),count//8)
    output[:,-fade:]*=np.linspace(1,0,fade,dtype=np.float32)
    if start:output[:,:RATE//50]*=np.linspace(0,1,RATE//50,dtype=np.float32)
    report=dict(policy='audible_ending_window_v1',raw_seconds=samples.shape[1]/RATE,target_seconds=seconds,
        musical_start_seconds=first/RATE,musical_end_seconds=last/RATE,threshold_rms=threshold,
        crop_start_seconds=start/RATE,crop_end_seconds=end/RATE,trailing_removed_seconds=(samples.shape[1]-end)/RATE,
        ending_fade_seconds=fade/RATE,tempo_changed=False,looped=False,silence_padded=False)
    return output,report
