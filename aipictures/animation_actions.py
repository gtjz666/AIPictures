"""Explicit UI-owned actions and Chinese starter clauses; no prompt-based model selection."""
ACTIONS={
 'walk':('走路','左右腿交替迈步，双臂反向摆动，脚掌依次抬起和落地，完成包含左右两步的完整原地行走周期。'),
 'idle':('待机','双脚稳定站在地面，身体轻微呼吸起伏，头部和手臂轻微自然运动，保持原地待机。'),
 'run':('跑步','左右腿交替蹬地和前摆，双臂屈肘反向摆动，包含双脚短暂腾空阶段，完成完整原地跑步周期。'),
 'jump':('跳跃','从站立屈膝蓄力，双脚蹬地同时起跳，空中收腿，然后双脚落地屈膝缓冲，最后恢复站立。'),
 'squat':('下蹲','双脚脚掌始终贴地，髋部先向后移动，双膝弯曲缓慢下蹲，躯干适度前倾保持平衡，低位短暂停留，然后伸髋伸膝恢复站立，不起跳。'),
}
ONE_SHOT_ACTIONS=frozenset(('jump','squat'))


def output_indices(action: str, count: int, length: int) -> list[int]:
    """Loops omit the duplicate endpoint; a one-shot jump retains its landing."""
    if action not in ACTIONS or count < 2 or length < count:
        raise ValueError('动作、输出帧数或原始帧数无效。')
    denominator = count - 1 if action in ONE_SHOT_ACTIONS else count
    return [round(i * (length - 1) / denominator) for i in range(count)]


def stage_label(action,phase):
    if action in ONE_SHOT_ACTIONS and phase>=1:return '恢复站立'
    phase=phase%1
    if action=='walk': return ('右脚接触','右脚承重','左腿经过','左脚前摆','左脚接触','左脚承重','右腿经过','右脚前摆')[int(phase*8)%8]
    if action=='run': return ('右脚接触','右腿承重','右腿蹬地','腾空换腿','左脚接触','左腿承重','左腿蹬地','腾空换腿')[int(phase*8)%8]
    if action=='idle': return '吸气起伏' if phase<.5 else '呼气回落'
    if action=='squat':
        for end,title in ((.08,'准备站立'),(.25,'髋部后移'),(.42,'屈膝下蹲'),(.58,'低位停留'),(.90,'伸髋起身'),(1.01,'恢复站立')):
            if phase<end:return title
    for end,title in ((.08,'准备'),(.20,'下蹲蓄力'),(.27,'蹬地起跳'),(.72,'空中姿态'),(.90,'落地缓冲'),(1,'恢复站立')):
        if phase<end: return title
