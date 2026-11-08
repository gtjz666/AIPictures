"""Source-video editing instructions and guards for assistant-generated text."""
import re


FORMAT='source_video_edit_v1'
# Quality defects only. Do not prohibit legitimate source pauses, repeats,
# camera changes, framing, expressions or motion blur.
QUALITY_NEGATIVE='主体身份无故变化，肢体结构破损，服装穿插，非预期文字水印'
FACE=r'表情|神情|笑容|微笑|大笑|哭泣|闭眼|睁眼|expression|smil|crying'
CAMERA=r'镜头|机位|构图|视角|朝向|近景|远景|全身|正面|侧面|camera|framing|shot|view'
POSE=r'站姿|站立|坐姿|双臂.*垂|双手.*垂|静止姿态|standing|seated|arms.*sides'
FACE_REQUEST=FACE+r'|情绪|开心|高兴|悲伤|难过|生气|愤怒|严肃|冷漠|平静|happy|sad|angry|emotion|calm'
POSE_REQUEST=POSE+r'|站着|坐着|坐下|静止|不动|stationary|sitting'
DETAIL=r'衣|裙|裤|袜|鞋|图案|[紫蓝红绿黑白金银棕灰]发|[紫蓝红绿黑棕金]眼|hair|eyes|shirt|dress|outfit|pattern'


def generated_constraints(positive:str,brief:str,negative:str)->tuple[str,str]:
    """Apply only inside explicit assistant planning, never to a user's prompt.

    A still-picture expression/pose is transient evidence, not an animation
    requirement. Keep such clauses when explicitly requested by the user.
    User exclusions remain byte-for-byte as supplied, after quality defaults.
    """
    forbidden=[pattern for pattern,request in ((FACE,FACE_REQUEST),(POSE,POSE_REQUEST)) if not re.search(request,brief,re.I)]
    if not re.search(CAMERA,brief,re.I):
        forbidden.append(r'固定机位|固定镜头|全身(?:可见|构图|入镜)|正面(?:朝向|视角)|面向镜头|fixed camera|full.body|front.facing')
    clauses=re.split(r'(?<=[，,；;。\n])',positive)
    # Keep compound appearance facts rather than deleting identity/clothing
    # merely because the same clause mentions a face graphic or a standing pose.
    kept=[clause for clause in clauses if re.search(DETAIL,clause,re.I) or
          not any(re.search(pattern,clause,re.I) for pattern in forbidden)]
    cleaned=''.join(kept).strip('，,；;。\n ')
    exclusions=QUALITY_NEGATIVE+('\n'+negative if negative.strip() else '')
    return cleaned,exclusions


def compile_prompt(text:str,has_image:bool,*,reference_role='appearance',reference_usage='')->str:
    if not has_image:
        appearance='Use the target appearance and style specified by the user below.'
    elif reference_role=='style':
        appearance=('Use <Picture 1> only for visual style, drawing technique and rendering. '
                    'The performer identity follows the user request, otherwise the source video; '
                    'do not substitute the picture character or its still pose.')
    elif reference_role=='custom':
        if not reference_usage.strip():raise ValueError('请填写参考图的自定义用法。')
        appearance=('Use <Picture 1> for the explicitly selected properties, not automatically for identity or pose. '
                    'Custom image usage (verbatim):\n'+reference_usage.strip())
    else:
        appearance=('The subject identity, clothing, proportions, colors and visual style come from <Picture 1>, '
                    'except for explicit user changes. Its still pose and composition do not define the animation. '
                    'The picture is an appearance reference, not the opening frame or a standing-pose anchor.')
    task='video editing + reference generation' if has_image else 'video editing'
    return (
        'subject_definitions:\n<Subject 1>: The target performer. '+appearance+' '
        'Its visible movement is the performance of the source actor in <Video 1>, adapted to the target anatomy.\n'
        '<Video 1>: The source clip being edited; the highest-priority reference for motion, action order, timing, '
        'movement direction, expressions and camera behavior.\n'
        'summary:\n['+task+'] The target video is an edited version of <Video 1>. '
        'Apply the requested appearance changes to its performer while retaining the source performance throughout.\n'
        'retention_analysis:\n'
        '<Subject 1> (throughout the source shots): attribute_transfer - Retain the appearance properties defined above. '
        'Use the source actor motion, balance, limb coordination and expressions rather than the picture pose.\n'
        '<Video 1> (performance and temporal structure): fully_preserved - Preserve the action phases and their original '
        'relative timing, body orientation, movement direction, shot boundaries and camera movement. '
        'Background and other edits follow explicit user requirements.\n'
        'Only explicit user changes override the corresponding properties or time ranges; all other motion follows <Video 1>. '
        'Use the actual guide frames rather than an inferred action description whenever they disagree.\n'
        'detailed_description:\n'
        'Render the requested target appearance consistently in the source performance.\n'
        '[Shot 1] Begin immediately in the movement phase visible at the start of <Video 1>, without adding a neutral '
        'standing introduction or a delay before the action. Follow the source performer through the complete supplied clip. '
        'Preserve the visible sequence, rhythm, pauses, repeated gestures, motion amplitude and direction. '
        'Retain coordinated feet, legs, hips, torso, head and arm movement wherever visible in the source; '
        'do not simplify a full-body performance into small isolated hand gestures. '
        'Adapt limb lengths to the target proportions while preserving the source movement intent, balance and contact phases. '
        'Follow the guide framing and camera changes instead of imposing a static portrait composition. '
        'Retain any source shot transitions at their corresponding moments. '
        'Do not invent, omit, mirror, reverse or retime movements unless explicitly requested.\n'
        'User requirements (preserved verbatim; user-entered action seconds refer to the output clip):\n'+text.strip()+'\n'
        'overall_soundscape:\nNo source audio is transferred.\nnon_diegetic_music:\nNone.')
