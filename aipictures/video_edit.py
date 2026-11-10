"""Numbered appearance/style inputs for actual source-video editing, no motion analysis."""
import json
import re
from pathlib import Path
from .multi_reference import bind_text
from .video_script import simple
from .storage import write_json

FORMAT='video_edit_multi_v1'


def bind_labels(text,references):
    bound=bind_text(text,[row['number'] for row in references])
    return re.sub(r'(?<![A-Za-z])Image\s+(\d+)(?!\d)',lambda m:f'<Picture {m[1]}>',bound)


def compile_prompt(text,references,*,reference_role='appearance',reference_usage=''):
    ids=[row['number'] for row in references]
    bound=bind_labels(text,references) if ids else text
    labels='\n'.join(f'<Picture {i+1}>: User reference image labelled 图{number}; use only the properties assigned by the user.' for i,number in enumerate(ids))
    if len(ids)==1:
        if reference_role=='style':labels+='\nDefault for this picture: visual style only; preserve source performer identity unless the user requests replacement.'
        elif reference_role=='custom':labels+='\nDefault picture usage: '+reference_usage
        else:labels+='\nDefault for this picture: target identity/appearance, excluding its still pose. Explicit user assignments override this default.'
    return ('subject_definitions:\n<Video 1>: The source video being edited.\n'+labels+
        '\nsummary:\n[video editing] Edit the actual source video according to the requested replacements and visual style. '
        'The video is the highest-priority reference for action sequence, timing, body orientation, expressions, camera movement and shot changes. '
        'Reference pictures supply only their assigned identity, appearance, clothing, style, composition or background properties. '
        'Do not copy another reference character or a still reference pose when only its style was requested.\n'
        'retention_analysis:\nKeep the source performance, interaction, motion rhythm and relative timing. Replace only explicitly requested properties. '
        'Keep source background and other subjects unless the user asks to edit them. Explicit user changes take priority in their stated scope. '
        'Do not reset to a standing introduction, mirror or reverse the action, or simplify it into unrelated gestures.\n'
        'User editing requirements (verbatim apart from numbered label mapping):\n'+bound+
        '\noverall_soundscape:\nGenerate sound matching the edited scene and any explicit music request. No unrequested speech.')


def organize(config,brief,seconds,style,references,folder,cancel,emit,*,exclusions='',session_factory=None):
    # The actual Ref2VA encoder reads every image and source frame. A second
    # VLM paraphrase can invert explicit style choices; never replace the request.
    from .engine import Cancelled
    from .motion_prompt import QUALITY_NEGATIVE
    from .workflow_library import digest
    if cancel.is_set():raise Cancelled('视频编辑要求整理已取消。')
    bind_text(brief,references);bind_text(exclusions,references)
    if not brief.strip():raise ValueError('请填写视频编辑要求。')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    write_json(folder/'request.json',dict(brief=brief,seconds=seconds,policy='direct_request_to_reference_encoder',video_content_analyzed=False,
        references=[dict(number=n,path=str(p),sha256=digest(Path(p))) for n,p in references.items()]))
    negative=QUALITY_NEGATIVE+('\n'+exclusions if exclusions.strip() else '')
    script=simple(brief,seconds,style,negative)
    script['shots'][0].update(camera='跟随源视频的机位、运动和镜头切换',sound='符合编辑后场景及用户配乐要求的原生声音')
    script['video_edit']=True;write_json(folder/'script.json',script)
    return script

