import json
from pathlib import Path

from aipictures.prompt_language import complete_pair, has_chinese, set_pair, texts, valid_pair


class Session:
    def __init__(self, reply, calls=None): self.reply, self.calls = reply, calls if calls is not None else []
    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        return json.dumps(self.reply, ensure_ascii=False), {}


class Editor:
    def __init__(self, value): self.value = value
    def toPlainText(self): return self.value


class Window:
    def __init__(self, positive, negative=''):
        self.positive, self.negative = Editor(positive), Editor(negative)
        self.intent_controller = type('C', (), {'generation_pair': None})()


def test_pair_is_text_only_and_keeps_empty_negative(tmp_path):
    calls = []
    session = Session({'positive_prompt': 'Keep the person from Image 1, use the pose from Image 2.',
                       'negative_prompt': ''}, calls)
    pair = complete_pair(session, {'positive_prompt': '保留图1人物，采用图2姿势。', 'negative_prompt': ''},
                         tmp_path/'run', ids=(1, 2), multi=True)
    assert pair['negative'] == ''
    assert pair['positive'].startswith('Keep the person from Image 1')
    assert len(calls) == 1
    # A text-only follow-up must not re-send the reference images.
    content = calls[0][1]['content']
    assert isinstance(content, str) and 'image_url' not in content
    saved = json.loads((tmp_path/'run'/'english.json').read_text('utf-8'))
    assert saved['images_read'] is False and saved['policy'] == 'same_session_text_only'


def test_untranslated_reply_keeps_chinese_plan_and_records_error(tmp_path):
    session = Session({'positive_prompt': '采用图1的人物和姿势', 'negative_prompt': ''})
    pair = complete_pair(session, {'positive_prompt': '采用图1的人物和姿势', 'negative_prompt': '不要文字'},
                         tmp_path/'bad', ids=(1,))
    assert pair == {}
    assert (tmp_path/'bad'/'english-error.json').is_file()


def test_missing_image_number_is_rejected(tmp_path):
    session = Session({'positive_prompt': 'Use the person from Image 3.', 'negative_prompt': 'No text'})
    assert complete_pair(session, {'positive_prompt': '图1人物', 'negative_prompt': '不要文字'},
                         tmp_path/'missing', ids=(1, 2)) == {}


def test_submission_uses_pair_only_while_visible_text_is_unchanged():
    w = Window('图1人物，图2姿势', '不要文字')
    assert texts(w) == ('图1人物，图2姿势', '不要文字')
    set_pair(w.intent_controller, w.positive.value, w.negative.value,
             'Person from Image 1, pose from Image 2', 'No text')
    assert texts(w) == ('Person from Image 1, pose from Image 2', 'No text')
    w.positive.value = '图1人物，图2姿势，再亮一点'
    assert texts(w) == ('图1人物，图2姿势，再亮一点', '不要文字')
    assert valid_pair(w.intent_controller.generation_pair, w.positive.value, w.negative.value) is False


def test_chinese_detection_ignores_reference_labels():
    assert has_chinese('图1的人物') and not has_chinese('Image 1')
    assert not has_chinese('')
