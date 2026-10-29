"""Explicit animation detail choices; never infer style or quality from prompts."""
DETAIL_PROFILES = {
    'native': {'title': '原生细节 · 768×1024', 'size': (768, 1024)},
    'preview': {'title': '快速预览 · 480×640', 'size': (480, 640)},
}
SAMPLERS = {'euler': 'Euler', 'dpmpp_2m': 'DPM++ 2M'}
COLOR_MODES = {'original':'保留生成原色（推荐）','reference':'参考配色校正（可选）'}


def detail_settings(profile='native', sampler='euler'):
    if profile not in DETAIL_PROFILES:
        raise ValueError('未知动画清晰度，请在“角色与生成”中重新选择。')
    if sampler not in SAMPLERS:
        raise ValueError('未知动画采样方式，请在“角色与生成”中重新选择。')
    selected=DETAIL_PROFILES[profile]
    return {'profile':profile,'title':selected['title'],'inference_canvas':list(selected['size']),
        'sampler':sampler,'scheduler':'simple','output_canvas':[768,1024],
        'post_enlargement':selected['size']!=(768,1024),'automatic_restoration':False}
