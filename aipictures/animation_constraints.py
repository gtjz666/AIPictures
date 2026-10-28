"""Explicit exclusions become short positive constraints for Animate's CFG-1 sampler."""
import re


def positive_restrictions(negative):
    rules=[(('多个人物','重复人物','分格','拼贴','多视图','三视图','设定图'),'画面只有一个角色和一个连续视角'),
        (('手','肢体','畸形','融合','扭曲'),'双臂双手结构完整，手指自然，手部颜色与参考一致'),
        (('脚','腿','鞋'),'双腿各连接一只脚，鞋底轮廓清晰，落地时脚底稳定'),
        (('色','褪','曝光','亮','色温'),'参考配色完整统一，整段曝光与色温稳定'),
        (('脸','发','服','身份','比例'),'人物身份、脸型、发型、服装与比例保持一致'),
        (('镜头','视角'),'镜头固定并沿用参考视角'),
        (('裁切','出框'),'头部与双脚始终完整入镜'),
        (('道具','物体'),'只保留参考图已有的物品，不添加手持物'),
        (('模糊','重影','抖动','突变'),'轮廓清晰且动作连续平稳'),
        (('文字','水印'),'画面纯净，不添加文字与标记'),
        (('复杂背景',),'背景简洁')]
    result=[]; custom=[]
    for clause in filter(None,re.split('[，,。;；\n]+',negative.strip())):
        clause=re.sub(r'^(?:不要|避免|禁止|不需要|不想)(?:出现|生成|添加)?\s*','',clause.strip())
        if not clause: continue
        matched=False
        for words,instruction in rules:
            if any(word in clause for word in words):
                if instruction not in result: result.append(instruction)
                matched=True
        if not matched: custom.append(clause)
    if custom: result.append('用户额外排除要求：避免出现'+ '、'.join(custom))
    return '；'.join(result)
