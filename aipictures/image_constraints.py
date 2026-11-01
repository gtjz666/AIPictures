"""Compile a few explicit composition requests; never infer models, LoRAs or styles."""
import re


def compile_constraints(text: str) -> dict:
    positive=[];negative=[];notes=[]
    # Negated clauses are not positive pose instructions.
    requested=re.sub(r'(?:不要|禁止|不需要|别)[^，,。；;\n]*',' ',text,flags=re.I)
    hands=re.search(r'双[手臂](?:自然下垂|放在身体两侧)|双臂自然下垂|'
        r'(?:hands|arms) (?:relaxed )?at (?:her|his|their|the) sides',requested,re.I)
    pockets=re.search(r'插兜|插[入在].*口袋|hands in pockets',requested,re.I)
    if hands and not pockets:
        positive.append('both hands clearly visible outside pockets, relaxed arms down at the sides')
        negative.extend(('hands in pockets','hidden hands'))
        notes.append('明确双手位于身侧：补充手部可见与不插兜约束。')
    one=re.search(r'单个物件|单个道具|只有一个|仅一[个只]|\bone (?:single )?(?:object|bottle|item|character)\b',requested,re.I)
    layout=re.search(r'多视图|网格|拼图|精灵图|多个|一组|并排|\b(?:sheet|grid|collage|multiple views)\b',requested,re.I)
    if one and not layout:
        negative.extend(('duplicate main subject','sprite sheet','contact sheet','collage','multiple views'))
        notes.append('明确单一主体：排除重复主体与多视图拼图。')
    return {'positive':', '.join(positive),'negative':', '.join(negative),'notes':notes,
            'model_or_lora_selection':False}


def apply_constraints(positive: str, negative: str, constraints: dict) -> tuple[str,str]:
    for name,value in (('positive',positive),('negative',negative)):
        extra=constraints.get(name,'')
        if extra and extra not in value:
            value=value.rstrip(' ,')+', '+extra if value.strip() else extra
        if name=='positive':positive=value
        else:negative=value
    return positive,negative
