from aipictures.action_intent import appearance_description


def test_switching_animation_removes_old_english_actions_but_keeps_appearance():
    text = 'red jacket, Squatting, crouching, idle, idling, walking in place, running, jump, standing still'
    assert appearance_description(text) == 'red jacket'


def test_action_cleanup_does_not_damage_character_or_style_words():
    assert appearance_description('catwalk fashion, jumper, red jacket') == 'catwalk fashion, jumper, red jacket'
