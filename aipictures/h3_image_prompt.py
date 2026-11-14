"""Reference-aware instructions without a lossy image-to-caption detour."""
from pathlib import Path
from .audio_prompt import TextSession
from .engine import Cancelled
from .multi_reference import image_ids
from .prompt_language import _request,has_chinese
from .storage import write_json
from .workflow_library import digest


def organize(config,brief,references,folder,cancel,emit,*,session_factory=None):
    if not references:
        from .professional_prompt import organize as text_organize
        return text_organize(config,brief,'',{},None,folder,cancel,emit,selected_kind='image',session_factory=session_factory)
    if cancel.is_set():raise Cancelled('提示词整理已取消。')
    missing=image_ids(brief)-set(references)
    if missing:raise ValueError('需求引用了尚未提供的参考图。')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    assets=[dict(number=n,path=str(p),sha256=digest(Path(p))) for n,p in references.items()]
    # The native visual encoder already sees the full images. Keep the actual
    # operation, source/target roles and exclusions instead of inventing captions.
    positive=brief.strip()
    write_json(folder/'request.json',dict(user_request=brief,images=assets,images_read=False,prompt_expander=False))
    emit('intent_stage',dict(message='正在翻译用户要求，不分析或解释参考图…'))
    if has_chinese(positive):
        with (session_factory or TextSession)(config,folder/'session',cancel,emit) as session:
            english,stats=_request(session,positive,'',ids=references)
        write_json(folder/'english.json',dict(result=english,stats=stats,images_read=False))
    else:english=dict(positive=positive,negative='')
    if cancel.is_set():raise Cancelled('提示词整理已取消。')
    if any(digest(Path(row['path']))!=row['sha256'] for row in assets):raise ValueError('整理期间参考图变化，本次结果未应用。')
    result=dict(plan=dict(positive_prompt=positive,negative_prompt='',timeline=[],observations=[],summary='按参考图关系编辑'),
        english=english,assets=assets,images_read=False,prompt_policy='h3_native_relations_v1',engine_released=True)
    write_json(folder/'result.json',result);return result
