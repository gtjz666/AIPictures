"""Explicit UI-owned actions and Chinese starter clauses; no prompt-based model selection."""
ACTIONS={
 'walk':('走路','左右腿交替迈步，双臂反向摆动，脚掌依次抬起和落地，完成包含左右两步的完整原地行走周期。'),
 'idle':('待机','双脚稳定站在地面，身体轻微呼吸起伏，头部和手臂轻微自然运动，保持原地待机。'),
 'run':('跑步','左右腿交替蹬地和前摆，双臂屈肘反向摆动，包含双脚短暂腾空阶段，完成完整原地跑步周期。'),
 'jump':('横版跳跃','2D横版游戏向前跳跃，先屈髋屈膝预备，髋部后移，脚趾蹬地；双臂与躯干按真实跳跃时序配合，上升后自然屈腿，下落时伸腿迎接地面，落地屈膝吸收冲击再恢复站立。整体跳跃轨迹由游戏引擎驱动，不烘焙进PNG。'),
 'squat':('下蹲','双脚脚掌始终贴地，髋部先向后移动，双膝弯曲缓慢下蹲，躯干适度前倾保持平衡，低位短暂停留，然后伸髋伸膝恢复站立，不起跳。'),
 'attack':('基础攻击','2D横版游戏徒手攻击，先小步打开前后站姿并屈膝，后脚掌蹬地、后脚跟自然抬起，髋、胸、肩先后转动带动前手快速出拳，另一拳护住下颌；短暂停顿后收拳，重心回稳，后脚回到站立。不要添加武器、敌人或特效。'),
 'custom':('自定义动作','按用户的动作说明执行完整动作。'),
}
PRESET_ACTIONS={key:value for key,value in ACTIONS.items() if key!='custom'}
ONE_SHOT_ACTIONS=frozenset(('jump','squat','attack','custom'))
V4_CLAUSES={
 'jump':'2D横版游戏跳跃姿态，短促蹬地，上升时一侧膝盖前提、另一腿后摆，手臂前后错开；顶点收腿，下落伸腿准备落地，短促缓冲后站立。不要双臂平行前伸。角色根部不烘焙垂直位移，由游戏引擎驱动跳跃轨迹。',
 'attack':'2D横版游戏徒手攻击，短暂向后蓄力，身体转重心向前出拳，另一只手保持防守；出拳后短暂停顿，再收拳恢复站立。不要添加武器、敌人或特效。',
}


def action_clause(action,revision=5):
    return V4_CLAUSES.get(action,ACTIONS[action][1]) if revision<5 else ACTIONS[action][1]


def output_indices(action: str, count: int, length: int) -> list[int]:
    """Loops omit the duplicate endpoint; a one-shot jump retains its landing."""
    if action not in ACTIONS or count < 2 or length < count:
        raise ValueError('动作、输出帧数或原始帧数无效。')
    denominator = count - 1 if action in ONE_SHOT_ACTIONS else count
    return [round(i * (length - 1) / denominator) for i in range(count)]


def stage_label(action,phase,revision=5):
    if action in ONE_SHOT_ACTIONS and phase>=1:return '恢复站立'
    phase=phase%1
    if revision>=5 and action in ('jump','attack'):
        stages=((.08,'重心预备'),(.22,'屈髋摆臂'),(.26,'脚趾蹬地'),(.40,'上升'),(.52,'腾空顶点'),(.70,'伸腿下落'),(.90,'屈膝吸收落地'),(1.01,'恢复站立')) if action=='jump' else (
            (.18,'打开站姿'),(.30,'脚髋带动肩胸'),(.37,'快速出拳'),(.47,'命中停顿'),(.80,'收拳回稳'),(1.01,'后脚归位'))
        return next(title for end,title in stages if phase<end)
    if action=='walk': return ('右脚接触','右脚承重','左腿经过','左脚前摆','左脚接触','左脚承重','右腿经过','右脚前摆')[int(phase*8)%8]
    if action=='run': return ('右脚接触','右腿承重','右腿蹬地','腾空换腿','左脚接触','左腿承重','左腿蹬地','腾空换腿')[int(phase*8)%8]
    if action=='idle': return '吸气起伏' if phase<.5 else '呼气回落'
    if action=='attack':
        return next(title for end,title in ((.22,'蓄力'),(.34,'出拳'),(.46,'命中停顿'),(.78,'收招'),(1.01,'恢复站立')) if phase<end)
    if action=='custom':return '自定义动作'
    if action=='squat':
        for end,title in ((.08,'准备站立'),(.25,'髋部后移'),(.42,'屈膝下蹲'),(.58,'低位停留'),(.90,'伸髋起身'),(1.01,'恢复站立')):
            if phase<end:return title
    for end,title in ((.06,'短促预备'),(.18,'蹬地上升'),(.38,'上升收腿'),(.62,'顶点姿态'),(.80,'下落伸腿'),(.93,'落地缓冲'),(1.01,'恢复站立')):
        if phase<end: return title
