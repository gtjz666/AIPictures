"""Explicit musical requirement organization and reusable English request pairs."""
import hashlib
import json
from pathlib import Path
import re
from difflib import SequenceMatcher
from .storage import write_json
from .engine import Cancelled
from .local_intent import LocalSession


class TextSession(LocalSession):
    def command(self,port):
        command=super().command(port)
        for flag in ('--mmproj','--image-min-tokens','--image-max-tokens'):
            i=command.index(flag);del command[i:i+2]
        if self.config.get('audio_prompt_cpu'):
            command[command.index('-ngl')+1]='0';command[command.index('--flash-attn')+1]='off'
            command+=['--device','none']
        return command

KEYS=('positive_prompt','negative_prompt','english_caption','english_avoid','english_requirement')
SCHEMA=dict(type='object',properties={key:dict(type='string') for key in KEYS},required=list(KEYS),additionalProperties=False)
SYSTEM='''You organize instrumental music requirements, not images or video. Return JSON only.
positive_prompt: a concise Chinese musical prompt, retaining the requested mood, scale, instrumentation, rhythmic weight, clear progression, climax and ending. Add concrete compatible orchestration and clean production details where useful. Do not change the requested style or ban its characteristic instruments. Do not add vocals, choir, lyrics, sound effects or a story. Never claim guaranteed audio quality.
negative_prompt: concise Chinese unwanted content and recording artifacts, preserving the user's explicit exclusions verbatim. Do not classify musical tension, powerful drums, brass or dissonance as unwanted noise when requested.
english_caption: faithful English music caption covering BOTH Chinese fields, including all explicit exclusions. Use clean, distinct instrumentation, clear separation and a natural ending. It is the actual single caption sent to the music model; there is no separate negative-conditioning input. Do not add unrequested restrictions. Respect the duration supplied in the request and keep music active throughout it with a brief natural release, no early fade or long silent tail.'''
SYSTEM+='\nenglish_avoid: an explicit English list of ALL negative_prompt items and the user exclusions, including each excluded instrument, voice type and recording artifact. Do not summarize specific exclusions as merely noise.'
SYSTEM+='\nWhen manual_prompt is supplied, preserve its musical choices and give those edited choices priority over conflicting original requirements. The duration control is authoritative.'
SYSTEM+='\nenglish_requirement: faithfully translate the primary user musical request (manual_prompt when supplied, otherwise requirement), preserving every mood and musical choice. Keep oppressive pressure explicit when requested. This is authoritative; english_caption may add only compatible orchestration suggestions.'


def fingerprint(positive,negative):
    return hashlib.sha256(json.dumps([positive.strip(),negative.strip()],ensure_ascii=False).encode()).hexdigest()


def normalize(value,brief,exclusions='',manual_prompt=''):
    value=value.copy();primary=(manual_prompt or brief).strip();suggestion=value['positive_prompt'].strip()
    # Preserve the user's words; do not display a near-identical paraphrase twice.
    if primary in suggestion:value['positive_prompt']=suggestion
    elif SequenceMatcher(None,primary,suggestion).ratio()>=.55:value['positive_prompt']=primary
    else:value['positive_prompt']=primary+'\n\n'+suggestion
    if len(value['positive_prompt'])>8000:value['positive_prompt']=primary
    if exclusions.strip():
        def parts(text):return [p.strip() for p in re.split('[、，,；;。\n]+',text) if p.strip()]
        def key(text):return re.sub(r'^(?:不要|禁止|避免|不含|没有|无)+','',text.strip())
        manual={key(part) for part in parts(exclusions)}
        extra=[part for part in parts(value['negative_prompt']) if key(part) not in manual]
        value['negative_prompt']=exclusions.strip()+('\n'+'、'.join(extra) if extra else '')
    if len(value['negative_prompt'])>4000:raise ValueError('避免内容过长，请精简后整理。')
    english=value['english_requirement'].strip()
    if value['english_caption'].strip()!=english:english+='\n'+value['english_caption']
    value['english_caption']=english+'\nAvoid: '+value['english_avoid']
    value.update(source_brief=brief,caption_fingerprint=fingerprint(value['positive_prompt'],value['negative_prompt']))
    return value


def organize(config,brief,seconds,folder,cancel,emit,*,exclusions='',manual_prompt='',session_factory=None):
    if cancel.is_set():raise Cancelled('音频提示词整理已取消。')
    if not config:raise ValueError('本地提示词助手尚未配置，可先直接填写完整配乐要求。')
    if not brief.strip() or len(brief)>8000 or len(exclusions)>4000:raise ValueError('请填写8000字以内的音频要求。')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    request=dict(requirement=brief,seconds=seconds,exclusions=exclusions,manual_prompt=manual_prompt)
    write_json(folder/'request.json',request);emit('audio_stage',dict(message='正在整理配乐提示词…'))
    with (session_factory or TextSession)(config,folder/'session',cancel,lambda *_:None) as session:
        raw,stats=session.complete([dict(role='system',content=SYSTEM),dict(role='user',content=json.dumps(request,ensure_ascii=False))],schema=SCHEMA,max_tokens=2400)
    write_json(folder/'response.json',dict(raw=raw,stats=stats))
    value=json.loads(raw)
    if not isinstance(value,dict) or any(not isinstance(value.get(key),str) or not value[key].strip() for key in KEYS):raise ValueError('音频提示词不完整，原输入保留。')
    if any(len(value[key])>8000 for key in KEYS):raise ValueError('音频提示词过长，请精简要求。')
    if not re.search('[\u4e00-\u9fff]',value['positive_prompt']) or not re.search('[A-Za-z]{3}',value['english_caption']):raise ValueError('音频提示词语言格式不符。')
    value=normalize(value,brief,exclusions,manual_prompt)
    if cancel.is_set():raise Cancelled('音频提示词整理已取消。')
    value['seconds']=seconds
    write_json(folder/'result.json',value);return value


def translate(session,positive,negative):
    schema=dict(type='object',properties=dict(caption=dict(type='string')),required=['caption'],additionalProperties=False)
    raw,_=session.complete([dict(role='system',content='Faithfully translate this instrumental music request and its exclusions to one concise English caption. Do not reorganize, add instruments, alter tempo, or drop exclusions. Return JSON.'),
        dict(role='user',content=json.dumps(dict(music=positive,avoid=negative),ensure_ascii=False))],schema=schema,max_tokens=1400)
    value=json.loads(raw)['caption'].strip()
    if not value:raise ValueError('英文配乐提示词为空，未开始生成。')
    return value
