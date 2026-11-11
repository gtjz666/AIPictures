"""Choose the dedicated audio engine from the user's request, without image analysis."""
import re


def resolve_kind(text,selection='auto'):
    if selection in ('music','sfx'):return selection
    text=re.sub(r'(?:不要|不需要|无需|没有|禁止|不含|避免|without|no\s+)[^，,。；;\n]+','',text,flags=re.I)
    text=re.sub(r'无(?:任何)?(?:背景音乐|配乐|音乐|音效|人声|歌词|合唱)','',text)
    # An explicit sound-effect request can also say "不要背景音乐".
    if re.search(r'音效|sound\s*effects?|\bsfx\b',text,re.I):return 'sfx'
    if re.search(r'配乐|音乐|旋律|作曲|\bbgm\b|\bmusic\b|soundtrack',text,re.I):return 'music'
    if re.search(r'脚步|碰撞|爆炸|剑|开门|关门|引擎|枪声|枪响|风声|雨声|按钮|提示音|击中|敲击|轰鸣|挥动|whoosh|footsteps?|explosion|gunshot',text,re.I):return 'sfx'
    return 'music'
