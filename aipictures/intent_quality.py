"""Bounded semantic repair for observed cross-species prompt leakage."""
import json
import re
from pathlib import Path

from .storage import write_json


def repair_anatomy(session, output: str, observations: dict, brief: str, folder: Path) -> str:
    data = json.loads(output)
    identity = observations.get('appearance', {}).get('identity', '')
    human = re.search(r'少女|女性|男性|女人|男人|女孩|男孩|人类|\b(?:human|woman|man|girl|boy)\b', identity, re.I)
    # User-requested transformations remain authoritative.
    transformation = re.search(r'变成|兽化|长出.*爪|猫娘|兽娘', brief)
    leaked = re.search(r'前爪|后爪|猫坐|四足', data.get('positive_prompt', ''))
    if not human or transformation or not leaked:
        return output
    timeline = data.get('timeline', [])
    schema = {'type': 'object', 'additionalProperties': False, 'properties': {
        'positive_prompt': {'type': 'string'},
        'descriptions': {'type': 'array', 'minItems': len(timeline), 'maxItems': len(timeline), 'items': {'type': 'string'}}},
        'required': ['positive_prompt', 'descriptions']}
    context = dict(user_request=brief, target=observations['appearance'],
                   positive_prompt=data['positive_prompt'], descriptions=[r['description'] for r in timeline])
    messages = [{'role': 'system', 'content':
        '校对跨物种动作迁移文本。目标是人类，保留目标的脸、头发、服装、配色和原动作顺序。'
        '将源动物的前爪/后爪和猫坐姿转换为人的手臂/腿与合理人体姿态。成品提示词直接写人类动作，'
        '不用“前爪转手”这样的解释，不加动物或新背景。每项descriptions对应原来的同一时间段。只返回指定JSON。'},
        {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}]
    raw, stats = session.complete(messages, schema=schema)
    repaired = json.loads(raw)
    if (not isinstance(repaired, dict) or set(repaired) != {'positive_prompt','descriptions'} or
        not isinstance(repaired['positive_prompt'], str) or not 1<=len(repaired['positive_prompt'])<=10000 or
        not isinstance(repaired['descriptions'], list) or len(repaired['descriptions']) != len(timeline) or
        any(not isinstance(v, str) or not 1<=len(v)<=1200 for v in repaired['descriptions'])):
        raise ValueError('动作结构校对未完成，原输入保留，未提交生成。')
    if re.search(r'前爪|后爪|猫坐|四足', repaired['positive_prompt']+' '.join(repaired['descriptions'])):
        raise ValueError('动作描述仍含源动物的身体结构，请补充目标人物的手臂动作后重新整理；未提交生成。')
    data['positive_prompt'] = repaired['positive_prompt']
    for row, text in zip(timeline, repaired['descriptions']): row['description'] = text
    write_json(folder/'anatomy-repair.json', dict(before=output, after=data, **stats))
    return json.dumps(data, ensure_ascii=False)
