"""Chinese editors with matching English request text; no translation on unchanged prompts.

The visible editors always stay Chinese.  A plan is organized once in Chinese and
the same private model session produces the English request pair without reading
the images again.  Only a manually edited Chinese prompt is translated again, and
that pass is text-only as well.  Empty negative prompts stay empty.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QTimer
from .storage import write_json

EN_SCHEMA = {'type': 'object', 'additionalProperties': False, 'properties': {
    'positive_prompt': {'type': 'string', 'maxLength': 10000},
    'negative_prompt': {'type': 'string', 'maxLength': 10000}},
    'required': ['positive_prompt', 'negative_prompt']}

SYSTEM = (
    '你是提示词翻译员。把给出的中文正向/反向提示词准确翻译成英文，只翻译，不改写创作目标、不补充风格或质量套话。'
    '把“图1”“图2”等编号写成 Image 1、Image 2；保留原数字、时刻、动作顺序和需要绘制的原文文字。'
    '反向词为空就返回空字符串；不要擅自增加排除项。译文必须全英文，不能保留中文句子。只返回指定JSON。')


def has_chinese(text):
    text = re.sub(r'(?:图\s*[一二三四五六七八九十\d]+|Image\s*\d+)', '', text, flags=re.I)
    return bool(re.search(r'[\u3400-\u9fff]', text))


def valid_pair(pair, positive, negative):
    return bool(pair and pair.get('positive') == positive and pair.get('negative') == negative)


def texts(window):
    """Actual request text: matching English pair when present, else the visible text."""
    positive, negative = window.positive.toPlainText(), window.negative.toPlainText()
    pair = getattr(getattr(window, 'intent_controller', None), 'generation_pair', None)
    if valid_pair(pair, positive, negative):
        return pair['positive_en'], pair['negative_en']
    return positive, negative


def set_pair(controller, positive, negative, positive_en, negative_en, source=''):
    controller.generation_pair = dict(positive=positive, negative=negative,
        positive_en=positive_en, negative_en=negative_en, source=str(source))


def clear_pair(controller):
    controller.generation_pair = None


def _request(session, positive, negative, *, ids=()):
    """One text-only completion in an already loaded private session."""
    payload = dict(positive_prompt=positive, negative_prompt=negative)
    raw, stats = session.complete([{'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], schema=EN_SCHEMA, max_tokens=3000)
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != set(EN_SCHEMA['required']) or any(not isinstance(v, str) for v in value.values()):
        raise ValueError('英文生成词结构不完整。')
    positive_en, negative_en = value['positive_prompt'].strip(), value['negative_prompt'].strip()
    if not positive_en:
        raise ValueError('英文正向词为空。')
    if negative.strip() and not negative_en:
        raise ValueError('英文反向词为空。')
    if not negative.strip():
        negative_en = ''
    # Required on-image text may legitimately stay Chinese; the request still has
    # to be English prose rather than an untranslated Chinese sentence.
    if not re.search(r'[A-Za-z]{3}', positive_en) or (negative_en and not re.search(r'[A-Za-z]{2}', negative_en)):
        raise ValueError('英文生成词缺少英文内容。')
    if ids:
        from .multi_reference import image_ids
        missing = image_ids(positive_en) - set(ids)
        if missing:
            raise ValueError('英文生成词引用了未添加的图' + '、'.join(str(n) for n in sorted(missing)) + '。')
    return dict(positive=positive_en, negative=negative_en), stats


def complete_pair(session, plan, folder, *, negative='', ids=(), multi=False):
    """Produce the English pair in the same organization session (text only).

    A malformed translation never discards the Chinese plan: the caller keeps the
    visible Chinese text and the submission gate retries before generation.
    """
    positive = str(plan.get('positive_prompt', '')).strip()
    chinese_negative = str(plan.get('negative_prompt', '')).strip()
    if not positive:
        return {}
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    request = dict(positive_prompt=positive, negative_prompt=chinese_negative, user_exclusions=str(negative or '').strip(),
                   images_read=False, multi=bool(multi))
    try:
        pair, stats = _request(session, positive, chinese_negative, ids=ids)
    except (ValueError, KeyError) as exc:
        write_json(folder/'english-error.json', dict(request=request, error=str(exc)))
        return {}
    write_json(folder/'english.json', dict(request=request, result=pair, stats=stats,
        images_read=False, policy='same_session_text_only'))
    return pair


def translate(config, positive, negative, folder, cancel, emit, *, session_factory=None):
    """Text-only English conversion for manually edited visible Chinese prompts."""
    from .local_intent import LocalSession
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder/'request.json', dict(positive=positive, negative=negative, images_read=False))
    with (session_factory or LocalSession)(config, folder, cancel, emit) as session:
        emit('intent_stage', {'message': '正在转换本次英文生成词…'})
        pair, stats = _request(session, positive.strip(), negative.strip())
    write_json(folder/'result.json', dict(**pair, stats=stats, images_read=False))
    return pair


def ensure_for_generation(window):
    """Window.enqueue gate. Manual edits get one text-only pass before submission."""
    w = window
    c = getattr(w, 'intent_controller', None)
    if c is None or w.api_controller.cloud:
        return False
    if w.generation_type.currentData() != 'image':
        return False
    if w.custom_graph is not None:
        return False
    if not w.connected:
        return False
    positive, negative = w.positive.toPlainText(), w.negative.toPlainText()
    if valid_pair(getattr(c, 'generation_pair', None), positive, negative):
        return False
    if not positive.strip() or not (has_chinese(positive) or has_chinese(negative)):
        return False
    if c.running or w.preparing:
        return True
    if w.current or w.pending:
        raise ValueError('请等待当前任务完成，再转换修改后的提示词。')
    if not c.config:
        # Without the local assistant the visible Chinese is submitted unchanged;
        # Z-Image/FLUX accept it, and the request stays identical to the UI.
        return False
    folder = c.data/'intent'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]+'_english')
    c.running = w.preparing = True; c.cancel_event.clear()
    for button in c.prompt_actions:
        button.setEnabled(False)
    w.generate_button.setEnabled(False); w.task_display.start(); w.progress.setRange(0, 0)
    w.status.setText('正在转换本次英文生成词…')
    def run(emit):
        from .motion_native_backend import release_shared
        release_shared({'url': w.client.url if w.connected else None}, cancel=c.cancel_event)
        return translate(c.config, positive, negative, folder, c.cancel_event, emit)
    def finish(kind, data):
        if kind == 'intent_stage':
            w.status.setText(data['message']); return
        if kind not in ('result', 'error', 'cancelled'):
            return
        c.running = w.preparing = False
        for button in c.prompt_actions:
            button.setEnabled(True)
        w.task_display.finish('completed' if kind == 'result' else 'cancelled' if c.cancel_event.is_set() else 'failed')
        w.generation_type_changed()
        if kind == 'result' and not c.cancel_event.is_set():
            if (positive, negative) != (w.positive.toPlainText(), w.negative.toPlainText()):
                c.notify('提示词已修改，旧的英文转换结果未应用。'); return
            set_pair(c, positive, negative, data['positive'], data['negative'], folder/'result.json')
            QTimer.singleShot(0, w.enqueue)
        else:
            c.notify('英文转换已取消。' if c.cancel_event.is_set() else '英文转换未完成：'+str(data))
    w.launch(run, finish)
    return True
