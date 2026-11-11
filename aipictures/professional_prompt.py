"""Professionalize the user's text. Image pixels never enter this assistant."""
import json
import re
from contextlib import nullcontext
from pathlib import Path
from .audio_prompt import TextSession
from .engine import Cancelled
from .storage import write_json
from .workflow_library import digest
from .multi_reference import LABEL,NUMBERS,image_ids

SCHEMA=dict(type='object',properties={k:dict(type='string') for k in ('positive_prompt','summary')},required=['positive_prompt','summary'],additionalProperties=False)
SYSTEM='''你只负责将用户文字要求整理为专业创作提示词，不看图、不分析图片内容，不推测参考图的性别、服装、外形、姿势或画风。
保留图1、图2等编号、来源/目标的方向、保留与修改的属性、动作顺序、反复与转换。用户要“图1的主体/动作不变，只换图2的画风”，不能改成图2的人物，不把风格参考的人物或姿势混入主体。
只专业化现有要求，不创造用户没提的背景、机位、全身站立、情绪或风格。positive_prompt用中文写成可执行指令，summary一句话概述。不做分析回复，不生成时间轴。
有实际参考动画时，动作直接跟随参考，文字只指定人物、画风和明确修改。没有参考动画时，完整写入用户自己描述的动作与先后顺序。只返回JSON。'''


def labels(text):
    def replace(match):
        v=match.group(1) or match.group(2)
        return '图'+str(NUMBERS.get(v,int(v) if v.isdigit() else 0))
    return LABEL.sub(replace,text)


def style_transfer(brief):
    """Ground explicit style-only edits in the user's labels, without reading images."""
    text=labels(brief)
    match=re.search(r'将\s*图(\d+)[^，。；\n]{0,45}?(?:美术风格|画风|风格)\s*(?:修改|改|转换|调整|变换|更换)(?:成|为)?\s*图(\d+)',text)
    if not match:return None
    source,style=match.groups()
    if not re.search(r'保留\s*图'+source+r'[^。\n]*(?:外形|模样|主体|人物|动作)',text):return None
    return f'以图{source}为主体参考，保留图{source}的人物身份、外形与动作。仅将美术风格转换为图{style}的画风与渲染方式。不得用图{style}的人物身份或姿势替代图{source}。\n用户要求：'+brief.strip()


def organize(config,brief,negative,references,motion,folder,cancel,emit,*,selected_kind='image',role='appearance',reference_usage='',output_seconds=4.,session_factory=None,**_):
    from .motion_prompt import QUALITY_NEGATIVE,DIRECT_MOTION_GUIDE,text_animation_prompt,generated_constraints
    from .prompt_language import complete_pair,has_chinese
    if cancel.is_set():raise Cancelled('提示词整理已取消。')
    if not brief.strip() or len(brief)>12000:raise ValueError('请填写12000字以内的创作要求。')
    references={int(n):Path(p) for n,p in references.items()};missing=image_ids(brief+negative)-set(references)
    if missing:raise ValueError('尚未添加'+ '、'.join('图'+str(i) for i in sorted(missing))+'。')
    assets=[dict(number=n,path=str(p),sha256=digest(p)) for n,p in references.items()]
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    request=dict(user_request=brief,user_exclusions=negative,available_images=list(references),has_motion_reference=bool(motion),
        kind=selected_kind,reference_role=role,reference_usage=reference_usage,images_read=False)
    write_json(folder/'request.json',request);emit('intent_stage',dict(message='正在专业化创作要求…'))
    guided=bool(references or motion)
    needs_model=not guided or selected_kind=='image' and has_chinese(brief+negative)
    with ((session_factory or TextSession)(config,folder/'session',cancel,lambda *_:None) if needs_model else nullcontext()) as session:
        if guided:
            # The image generator already sees the real references. Replacing
            # their identity with a textual reconstruction reduces fidelity.
            value=dict(positive_prompt=labels(brief),summary='按当前要求编辑参考素材')
            write_json(folder/'response.json',dict(policy='direct_reference_instruction',images_read=False,rewritten=False))
        else:
            raw,stats=session.complete([dict(role='system',content=SYSTEM),dict(role='user',content=json.dumps(request,ensure_ascii=False))],schema=SCHEMA,max_tokens=1800)
            write_json(folder/'response.json',dict(raw=raw,stats=stats));value=json.loads(raw)
        text=value.get('positive_prompt')
        if not isinstance(text,str) or not text.strip():raise ValueError('专业提示词为空，原输入保留。')
        if image_ids(text)-set(references):raise ValueError('整理结果引用了未提供的图，原输入保留。')
        exclusions=negative.strip() if selected_kind=='image' else QUALITY_NEGATIVE+('\n'+negative.strip() if negative.strip() else '')
        if selected_kind=='image':
            text=style_transfer(brief) or text.strip()
            if not guided:text+='\n用户明确要求（优先保留）：'+brief.strip()
        elif motion:
            text,exclusions=generated_constraints(text,brief+'\n'+reference_usage,negative)
            text=text+'\n'+DIRECT_MOTION_GUIDE
        else:text,exclusions=text_animation_prompt(text,brief,negative,reference_usage)
        if len(text)>16000:raise ValueError('专业提示词过长，请精简要求。')
        exclusions=negative.strip()
        plan=dict(kind=selected_kind,summary=value.get('summary') or '创作要求已整理',positive_prompt=text,negative_prompt=exclusions,
            timeline=[],observations=[],questions=[])
        english=(complete_pair(session,plan,folder,negative=negative,ids=references,multi=bool(references)) if session is not None else
                 dict(positive=text,negative=exclusions)) if selected_kind=='image' else {}
    if cancel.is_set():raise Cancelled('提示词整理已取消。')
    if any(digest(Path(row['path']))!=row['sha256'] for row in assets):raise ValueError('整理期间参考素材发生变化，原结果未应用。')
    result=dict(schema_version=2,plan=plan,english=english,assets=assets,images_read=False,observations={},
        policy='numbered_references_v1' if len(references)>1 else 'text_professional_v1',
        prompt_policy='direct_reference_v3' if motion else 'text_requirements_v3',
        request=dict(brief=brief,negative=negative,selected_kind=selected_kind,reference_role=role,reference_usage=reference_usage),
        route=('h3_reference' if motion else 'h3') if selected_kind=='animation' else 'flux_reference' if references else 'zimage',
        model=config.get('name','本地文字助手'),status='ready',engine_released=True,timeline_clock='output')
    write_json(folder/'plan.json',result);write_json(folder/'result.json',result);return result
