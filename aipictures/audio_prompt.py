"""Explicit musical requirement organization and reusable English request pairs."""
import hashlib
import json
from pathlib import Path
import re
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

SECTIONS=(('musical_intent','方向与情绪'),('instrumentation','配器与声部'),
    ('rhythm_and_dynamics','节奏与力度'),('development','结构与收尾'),('production','音色与混音'))
KEYS=tuple(key for key,_ in SECTIONS)+('exclusion_quotes',)
SCHEMA=dict(type='object',properties={**{key:dict(type='string',minLength=1) for key,_ in SECTIONS},
    'exclusion_quotes':dict(type='array',items=dict(type='string'))},required=list(KEYS),additionalProperties=False)
DEFAULT_AVOID=('非要求的人声与歌词、意外削波与数字爆音。','Unrequested vocals or lyrics, accidental digital clipping and pops.')
# Include only terms actually present, rather than examples that the translator
# can accidentally copy into a different arrangement.
INSTRUMENT_TERMS={'钢琴':'piano','小提琴':'violin','中提琴':'viola','大提琴':'cello','低音提琴':'double bass',
    '木琴':'xylophone','颤音琴':'vibraphone','铃鼓':'tambourine','竖琴':'harp','圆号':'horn',
    '长号':'trombone','小号':'trumpet','定音鼓':'timpani','军鼓':'snare','长笛':'flute',
    '单簧管':'clarinet','双簧管':'oboe','吉他':'guitar','贝斯':'bass','合成器':'synth'}
SYSTEM='''你是器乐编曲师。将聊天式需求改写为可直接用于音乐生成的专业编曲要求，只输出JSON，不与用户对话。
保留原本情绪、用途、乐器、节拍、力度、排除要求；manual_prompt是用户修改稿，优先于冲突的原需求。简短需求要补全相容的音乐细节，完整需求则整理而不重复。不要把原话拼在成稿前，也不要仅换几个同义词。输出以下五个互补的中文字段，总计约180–350字：
musical_intent：曲风、用途和细腻情绪。舒缓但悲伤应兼顾两者；压迫、宏大应有相应重量；背景音乐保持克制。
instrumentation：选择相容的少量乐器，并写清谁负责旋律、和声、低音、节奏。用户限定独奏时只有该乐器，不自动加入乐队。不要所有风格都用管弦乐。
rhythm_and_dynamics：速度、节奏疏密、力度变化。已有BPM、拍号必须保留；未指定可选相容的速度或大致范围。安静配乐不强行推向宏大高潮。
development：用开场／中段／末段描述适合所选长度的发展和自然收尾，音乐持续到结束才短暂释音。不要自动写绝对秒数或时间轴，不安排提前长淡出或静音。
production：符合风格的触键／奏法、音色细节、声部分离、空间与动态。不承诺绝对音质，不额外编故事。
exclusion_quotes：从用户原文中逐字摘录的禁止内容，字符串数组；没有就[]。只摘取primary（manual_prompt非空时为manual_prompt，否则requirement）和exclusions中的原话，不自行扩充禁用乐器或风格。
五个正向字段用于具体编曲，不要写多余禁令：未提到某乐器不等于禁止该乐器；柔和不等于必须禁用铜管、打击乐和电子音色。不要添加人声、合唱、歌词、音效或情节。音乐性的紧张、鼓击、失谐、Lo-fi质感不自动属于杂音。'''


def fingerprint(positive,negative):
    return hashlib.sha256(json.dumps([positive.strip(),negative.strip()],ensure_ascii=False).encode()).hexdigest()


def normalize(value,brief,exclusions='',manual_prompt=''):
    value=value.copy()
    if not re.search('静音|无声|静默',manual_prompt or brief):
        # The real arranger added an unrequested "last second of silence".
        # Use a musical release, consistent with the full-duration audio policy.
        value['development']=re.sub(r'最后\s*[\d.一二三四五六七八九十]+\s*秒(?:的)?(?:静音|无声|静默)(?:收尾|结束)?','末尾自然释音收束',value['development'])
    # The renderer generates a small duration reserve. Unrequested absolute
    # seconds in a new arrangement would contradict that longer raw render.
    timed=re.search(r'(?:第|前|后|在|最后)\s*\d+(?:\.\d+)?\s*秒|\d+(?:\.\d+)?\s*[-–至]\s*\d+(?:\.\d+)?\s*秒',manual_prompt or brief)
    if not timed:
        for key,_ in SECTIONS:
            text=re.sub(r'前\s*\d+(?:\.\d+)?\s*秒','开场',value[key])
            text=re.sub(r'\d+(?:\.\d+)?\s*秒后','随后',text)
            value[key]=re.sub(r'\d+(?:\.\d+)?(?:\s*[-–至]\s*\d+(?:\.\d+)?)?\s*秒','',text)
    # Keep chat provenance separately. The usable prompt is the arranger's brief.
    value['positive_prompt']='\n'.join(f'{title}：{value[key].strip()}' for key,title in SECTIONS)
    if len(value['positive_prompt'])>8000:raise ValueError('配乐提示词过长，请精简要求。')
    primary=(manual_prompt or brief).strip();negative=exclusions.strip()
    ignored=[]
    # Only quoted user constraints become bans. Do not turn the assistant's
    # chosen palette into invented exclusions such as "no percussion/synths".
    # Preserve common explicit bans even if the model returns an empty list.
    explicit=re.findall(r'(?:不要|禁止|避免|不含|不需要|不想要|不能有)[^，,。；;\n!?！？]+',primary)
    for quote in explicit+value['exclusion_quotes']:
        quote=quote.strip()
        if quote and (quote in primary or quote in exclusions):
            if quote not in negative:negative+=('\n' if negative else '')+quote
        elif quote:ignored.append(quote)
    if not negative:negative=DEFAULT_AVOID[0]
    if len(negative)>4000:raise ValueError('避免内容过长，请精简后整理。')
    value['negative_prompt']=negative;value['ignored_exclusion_quotes']=ignored
    value.update(source_brief=brief,prompt_policy='professional_music_v2',caption_fingerprint=fingerprint(value['positive_prompt'],negative))
    return value


def organize(config,brief,seconds,folder,cancel,emit,*,exclusions='',manual_prompt='',session_factory=None):
    if cancel.is_set():raise Cancelled('音频提示词整理已取消。')
    if not config:raise ValueError('本地提示词助手尚未配置，可先直接填写完整配乐要求。')
    if not brief.strip() or len(brief)>8000 or len(exclusions)>4000:raise ValueError('请填写8000字以内的音频要求。')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    request=dict(requirement=brief,seconds=seconds,exclusions=exclusions,manual_prompt=manual_prompt)
    write_json(folder/'request.json',request);emit('audio_stage',dict(message='正在整理配乐提示词…'))
    with (session_factory or TextSession)(config,folder/'session',cancel,lambda *_:None) as session:
        # A complete manual edit replaces the old brief for planning. Do not
        # expose conflicting historical genres as a second active instruction.
        active_request=dict(task='将以下需求编写成专业器乐配乐提示词，补全五个中文字段；exclusion_quotes仅摘录用户明确禁止的原话。',**request)
        active_request['requirement']=manual_prompt or brief
        active_request.pop('seconds')
        active_request['duration_context']='短配乐，发展紧凑' if seconds<=30 else '中等篇幅配乐，段落连贯' if seconds<=90 else '较长配乐，逐层发展'
        write_json(folder/'model-request.json',active_request)
        raw,stats=session.complete([dict(role='system',content=SYSTEM),dict(role='user',content=json.dumps(active_request,ensure_ascii=False))],schema=SCHEMA,max_tokens=2000)
        write_json(folder/'response.json',dict(raw=raw,stats=stats));value=json.loads(raw)
        if not isinstance(value,dict) or any(not isinstance(value.get(key),str) or not value[key].strip() for key,_ in SECTIONS):raise ValueError('配器、节奏或结构提示词不完整，原输入保留。')
        if not isinstance(value.get('exclusion_quotes'),list) or any(not isinstance(quote,str) for quote in value['exclusion_quotes']):raise ValueError('避免内容格式不正确，原输入保留。')
        if any(len(value[key])>8000 for key,_ in SECTIONS):raise ValueError('音频提示词过长，请精简要求。')
        if any(not re.search('[\u4e00-\u9fff]',value[key]) for key,_ in SECTIONS):raise ValueError('音频提示词语言格式不符。')
        value=normalize(value,brief,exclusions,manual_prompt)
        emit('audio_stage',dict(message='正在准备专业编曲的英文请求…'))
        value['english_caption']=translate(session,value['positive_prompt'],value['negative_prompt'],record=folder/'translation.json')
    if cancel.is_set():raise Cancelled('音频提示词整理已取消。')
    value['seconds']=seconds
    write_json(folder/'result.json',value);return value


def translate(session,positive,negative,*,record=None,compact=True):
    schema=dict(type='object',properties=dict(caption=dict(type='string'),avoid=dict(type='string')),
        required=['caption','avoid'],additionalProperties=False)
    glossary={zh:en for zh,en in INSTRUMENT_TERMS.items() if zh in positive+negative}
    style=('Use one compact 90-120 word paragraph covering the musical choices from all sections. Omit repetition and scene-use examples, not musical choices.' if compact else
        'This is an authoritative user-edited prompt. Translate faithfully without condensing, rearranging, adding musical choices or dropping details.')
    raw,stats=session.complete([dict(role='system',content='Translate this finished Chinese instrumental-music brief into English. '+style+' Return JSON: caption translates music; avoid separately translates ALL input avoid items. Never leave avoid empty when its input is nonempty. Preserve mood, instruments and roles, BPM/meter, energy, development, ending and production. Use instrument_glossary literally. Do not invent instruments, bans, comparisons or Chinese characters.'),
        dict(role='user',content=json.dumps(dict(task='Translate into ENGLISH, not Chinese. Return caption and a separate English avoid list. '+style+' Preserve all named instruments using instrument_glossary and every exclusion.',music=positive,avoid=negative,instrument_glossary=glossary),ensure_ascii=False))],schema=schema,max_tokens=900 if compact else 1400)
    if record:write_json(record,dict(raw=raw,stats=stats))
    result=json.loads(raw);caption=result.get('caption');avoid=result.get('avoid')
    if not isinstance(caption,str) or not isinstance(avoid,str) or not caption.strip() or negative.strip() and not avoid.strip():raise ValueError('英文配乐或避免内容不完整，未开始生成。')
    value=caption.strip()+('\nAvoid: '+avoid.strip() if negative.strip() else '')
    if re.search('[\u4e00-\u9fff]',value):raise ValueError('英文配乐提示词语言不符，未开始生成。')
    if any(en.casefold() not in value.casefold() for en in glossary.values()):raise ValueError('英文配乐提示词遗漏指定乐器，原输入保留，未开始生成。')
    return value
