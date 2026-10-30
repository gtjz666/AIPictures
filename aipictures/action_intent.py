"""Local, explicit Chinese action vocabulary; no remote translation service."""
import re
from dataclasses import asdict, dataclass, field
from .prompt_text import APPEARANCE


@dataclass
class ActionIntent:
    action: str | None = None
    direction: str = 'right'
    direction_explicit: bool = False
    pace: str = 'normal'
    english: str = ''
    recognized: list[str] = field(default_factory=list)
    unmatched: str = ''
    negated: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


VOCAB = {
    'idle': ('待机','呼吸'),
    'walk': ('行走', '走路', '步行', '迈步', '走动', '散步'),
    'reach': ('向前伸手', '伸出手', '伸手', '伸直手臂'),
    'stand': ('站立', '站着', '站好', '静止', '不动'),
    'run': ('奔跑', '跑步', '跑动'),
    'jump': ('跳跃', '跳起来', '起跳'),
    'squat': ('下蹲','蹲下','深蹲','蹲伏'),
}
ACTION_EN = {
    'idle':'standing idle with subtle breathing',
    'walk': 'walking in place, alternating left and right steps, natural opposite arm swing',
    'reach': 'one arm reaching forward at chest height',
    'stand': 'standing still upright, arms relaxed at sides',
    'run': 'running', 'jump': 'jumping',
    'squat':'squatting with both feet planted, hips moving backward and knees bent',
}
TRANSLATIONS = {
    '侧视': 'strict side profile', '侧面': 'strict side profile',
    '全身': 'full body, entire head and feet visible', '蓝色头发': 'navy-blue hair', '蓝发': 'navy-blue hair',
    '短发': 'short bob hair', '白色衬衫': 'white blouse', '黑色袜子': 'black knee-high socks',
    '棕色鞋': 'brown loafers', '浅蓝色背景': 'plain pale-blue background',
    '白色背景': 'plain white background', '保持一致': 'consistent character and outfit',
    '人物一致': 'consistent character and outfit', '动漫': '2D anime illustration',
}
TRANSLATIONS.update(APPEARANCE)


def parse_intent(text):
    result = ActionIntent()
    remaining = text.strip()
    from .animation_actions import ACTIONS
    for action,(_,clause) in ACTIONS.items():
        if clause in remaining:
            result.action=action; result.recognized.append(clause)
            remaining=remaining.replace(clause,' ')
    # "慢走动画" contains the accidental substring "走动" across the noun boundary.
    for noun in ('动画序列帧','动画帧','动画','序列帧','精灵图'):
        remaining = remaining.replace(noun,' ')
    # Remove negated actions before searching positives, including mixed instructions.
    for key, words in VOCAB.items():
        for word in sorted(words, key=len, reverse=True):
            pattern = r'(?:不要|不需要|不想|不是|禁止|别|无需|不)\s*(?:再|一直|继续)?\s*' + re.escape(word)
            if re.search(pattern, remaining):
                result.negated.append(key)
                remaining = re.sub(pattern, '', remaining)
    hits = []; matched_words=[]
    for key, words in VOCAB.items():
        for word in sorted(words, key=len, reverse=True):
            if word in remaining:
                hits.append((remaining.rfind(word), key)); result.recognized.append(word)
                matched_words.append(word)
    if hits: result.action = max(hits)[1]
    for word in sorted(matched_words,key=len,reverse=True): remaining=remaining.replace(word,' ')
    # English action prompts remain usable, and avoid matching e.g. "catwalk".
    if not result.action:
        for key, pattern in [('walk', r'\bwalk(?:ing)?\b'), ('reach', r'\breach(?:ing)?\b'),
                             ('stand', r'\bstand(?:ing)?\b'), ('run', r'\brunn?ing\b'), ('jump', r'\bjump(?:ing)?\b'),
                             ('squat',r'\b(?:squat(?:ting)?|crouch(?:ing)?)\b')]:
            if re.search(pattern, remaining, re.I): result.action = key; break
    phrases = []
    for words, attr, value in [
        (('向左', '朝左', '面朝左'), 'direction', 'left'),
        (('向右', '朝右', '面朝右'), 'direction', 'right'),
        (('慢走', '慢速', '缓慢', '慢慢'), 'pace', 'slow'),
        (('快走', '快速', '加快'), 'pace', 'fast'),
    ]:
        for word in sorted(words, key=len, reverse=True):
            if word in remaining:
                setattr(result, attr, value); result.recognized.append(word)
                if attr=='direction': result.direction_explicit=True
                if attr == 'pace' and not result.action: result.action = 'walk'
                remaining = remaining.replace(word, ' ')
    for zh, en in sorted(TRANSLATIONS.items(), key=lambda pair: -len(pair[0])):
        if zh in remaining:
            result.recognized.append(zh); remaining = remaining.replace(zh, ' '+en+' ')
    if result.action: phrases.insert(0, ACTION_EN[result.action])
    # Preserve English verbatim; unsupported Chinese is reported instead of fake translation.
    english = re.sub(r'[\u3400-\u9fff]+', ' ', remaining)
    english = re.sub(r'[，。；、]+', ', ', english)
    english = re.sub(r' +',' ',english).strip(' ,，。；;!！')
    if english: phrases.append(english)
    for word in ('请', '帮我', '生成', '制作', '一个', '一张', '人物', '角色', '动画', '序列帧',
                 '精灵图', '原地', '自然', '正常', '循环', '的', '并且', '然后', '而是', '保持', '参考图'):
        remaining = remaining.replace(word, '')
    result.unmatched = ''.join(re.findall(r'[\u3400-\u9fff]+', remaining))
    result.english = ', '.join(dict.fromkeys(phrases))
    return result


def walk_intent(text):
    """The selected animation type owns the action; text supplies direction/appearance."""
    result = parse_intent(text)
    appearance=parse_intent(appearance_description(text)).english
    for phrase in ACTION_EN.values(): appearance=appearance.replace(phrase,'')
    result.action = 'walk'
    result.english = ACTION_EN['walk'] + (', ' + appearance.strip(' ,') if appearance.strip(' ,') else '')
    return result


def appearance_description(text):
    """Remove conflicting pose commands when the UI has already selected an animation."""
    from .animation_actions import ACTIONS
    for _,clause in ACTIONS.values(): text=text.replace(clause,' ')
    for noun in ('动画序列帧','动画帧','动画','序列帧','精灵图'): text=text.replace(noun,' ')
    for words in VOCAB.values():
        for word in sorted(words,key=len,reverse=True):
            text=re.sub(r'(?:不要|不需要|不想|不是|禁止|别|无需|不)\s*'+re.escape(word),' ',text)
            text=text.replace(word,' ')
    for phrase in (*ACTION_EN.values(),'双臂自然下垂','双脚平稳接触地面','保持站立','arms relaxed at sides'):
        text=text.replace(phrase,' ')
    text=re.sub(r'\b(?:stand(?:ing)?(?: still)?|walk(?:ing)?(?: in place)?|reach(?:ing)?(?: forward)?|'
                r'run(?:ning)?|jump(?:ing)?|squat(?:ting)?|crouch(?:ing)?|idl(?:e|ing))\b',
                ' ',text,flags=re.I)
    text=re.sub(r'[，,；;。\n]+',', ',text)
    return re.sub(r' +',' ',text).strip(' ,')
