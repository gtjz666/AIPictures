"""Chinese starter text; generation type owns animation and LoRA stays manual."""
from .animation_actions import ACTIONS
COMMON_POSITIVE='侧视，全身，头部与双脚完整入镜，人物居中，身体比例一致，轮廓清晰，背景简洁'
COMMON_NEGATIVE=('多个人物，重复人物，多余手臂，多余腿部，多余手指，缺失肢体，肢体融合，'
    '关节扭曲，手脚畸形，头部裁切，脚部裁切，人物出框，人物设定图，三视图，多视图，'
    '画面分格，拼贴，多余道具，颜色缺失，局部褪色，模糊，重影，文字，水印，复杂背景')
ANIMATION_NEGATIVE=('人物身份变化，脸部变化，发型变化，发色变化，服装变化，身体比例变化，'
    '视角变化，镜头移动，人物大小变化，画面抖动，动作突变，脚底滑动')


def default_prompts(walking=False,reference=False,action='walk'):
    subject='参考图中的同一角色，保持一致，配色一致' if reference else '单个角色'
    positive=subject+'，'+COMMON_POSITIVE
    if walking:
        positive+='，固定镜头，'+ACTIONS[action][1]
    else:
        positive+='，自然站立，双臂自然下垂，双脚平稳接触地面'
    negative=COMMON_NEGATIVE+('，'+ANIMATION_NEGATIVE+'，多余脚掌，重复鞋尖，分叉鞋底，双层鞋底，鞋子重影' if walking else '')
    if walking and action not in ('run','jump'): negative+='，脚部悬空'
    return positive,negative
