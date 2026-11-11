"""Text-only sound-effect instructions, without musical arrangement assumptions."""
import json
import re
from pathlib import Path
from .audio_prompt import TextSession,fingerprint
from .engine import Cancelled
from .storage import write_json


def organize(config,brief,seconds,folder,cancel,emit,*,session_factory=None):
    if cancel.is_set():raise Cancelled('音效需求整理已取消。')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    write_json(folder/'request.json',dict(requirement=brief,seconds=seconds,kind='sfx'))
    emit('audio_stage',dict(message='正在整理游戏音效要求…'))
    schema=dict(type='object',properties=dict(caption=dict(type='string')),required=['caption'],additionalProperties=False)
    with (session_factory or TextSession)(config,folder/'session',cancel,lambda *_:None) as session:
        raw,stats=session.complete([dict(role='system',content='Write a concise professional ENGLISH sound-effect generation instruction in at most 40 words, faithfully from the user request. Preserve the sound sources, event order/count, material, dynamics, timing, space and every explicit exclusion. Describe audible features. Never invent music, instruments, dialogue or extra events. Do not turn this into a music arrangement. Output JSON with caption only.'),
            dict(role='user',content=json.dumps(dict(requirement=brief,duration_seconds=seconds),ensure_ascii=False))],schema=schema,max_tokens=700)
    write_json(folder/'response.json',dict(raw=raw,stats=stats));caption=json.loads(raw).get('caption')
    if not isinstance(caption,str) or not caption.strip() or re.search('[\u4e00-\u9fff]',caption):raise ValueError('英文音效要求不完整，原输入保留。')
    if cancel.is_set():raise Cancelled('音效需求整理已取消。')
    result=dict(source_brief=brief,positive_prompt=brief,negative_prompt='',english_caption=caption.strip(),
        caption_fingerprint=fingerprint(brief,''),seconds=seconds,kind='sfx',images_read=False)
    write_json(folder/'result.json',result);return result
