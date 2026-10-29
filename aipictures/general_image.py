"""General image creation: explicit reference weighting, no inferred pose or subject."""
from .action_intent import TRANSLATIONS
from .prompt_text import translate_vocabulary
from .workflow import build_workflow

VOCABULARY = {
    **TRANSLATIONS,
    '正面全身': 'front view, full body', '正面视图': 'front view', '正面': 'front view',
    '面向镜头': 'facing the camera', '背面视图': 'back view', '背面': 'back view',
    '四分之三视角': 'three-quarter view', '三分之四视角': 'three-quarter view',
    '俯视图': 'top-down view', '俯视': 'top-down view', '仰视': 'low angle view',
    '等距视角': 'isometric view', '等距': 'isometric',
    '坐在木椅上': 'sitting on a wooden chair', '坐姿': 'sitting', '蹲姿': 'crouching',
    '站立': 'standing', '伸手': 'reaching forward', '双人': 'two people', '两个人': 'two people',
    '少女': 'young woman', '青年': 'young adult', '战士': 'warrior', '魔法师': 'wizard',
    '短发': 'short hair', '白色上衣': 'white top', '黑色短裤': 'black shorts',
    '紫色头发': 'purple hair', '皮肤': 'skin', '棕色皮靴': 'brown leather boots',
    '游戏道具': 'game prop', '单个物件': 'one object', '木箱': 'wooden crate',
    '金属宝箱': 'metal treasure chest', '药水瓶': 'potion bottle', '红色药水': 'red potion',
    '石桥': 'stone bridge', '森林': 'forest', '城镇': 'town', '街道': 'street',
    '背景场景': 'environment background', '无人': 'no people', '远景': 'wide establishing shot',
    '黄昏': 'dusk', '暖色灯光': 'warm lighting', '雨夜': 'rainy night',
    '写实': 'photorealistic', '水彩': 'watercolor painting', '像素画': 'pixel art',
    '手绘': 'hand painted', '高清': 'highly detailed', '保持原有配色': 'preserve original colors',
    '保持服装': 'preserve the outfit', '保持发型': 'preserve hairstyle',
    '保持参考图中的角色身份': 'preserve the identity of the character in the reference image',
}


def positive_text(text):
    # Unknown Chinese must not be silently erased or replaced by a standing pose.
    return translate_vocabulary(text, VOCABULARY)


def reference_workflow(request, reference, weight=.65):
    """Reference supplies image embeddings; fresh noise permits new views/composition."""
    if not 0 <= weight <= 1.5:
        raise ValueError('参考强度范围为 0–1.5')
    graph = build_workflow(request)
    if not reference or weight == 0:
        return graph
    model = graph['5']['inputs']['model']
    graph.update({
        'reference': {'class_type': 'LoadImage', 'inputs': {'image': reference}},
        'reference_adapter': {'class_type': 'IPAdapterModelLoader', 'inputs': {
            'ipadapter_file': 'ip-adapter-plus_sdxl_vit-h.safetensors'}},
        'reference_vision': {'class_type': 'CLIPVisionLoader', 'inputs': {
            'clip_name': 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'}},
        'reference_condition': {'class_type': 'IPAdapterAdvanced', 'inputs': {
            'model': model, 'ipadapter': ['reference_adapter', 0], 'image': ['reference', 0],
            'clip_vision': ['reference_vision', 0], 'weight': weight, 'weight_type': 'linear',
            'combine_embeds': 'concat', 'start_at': 0., 'end_at': .8, 'embeds_scaling': 'V only'},
            '_meta': {'title': '参考图强度', 'aipictures_reference_weight': True}},
    })
    graph['5']['inputs']['model'] = ['reference_condition', 0]
    return graph


def bind_reference_weight(graph, weight):
    """Only our documented knob; never guess which adapter in a custom graph is identity."""
    for node in graph.values():
        if node.get('_meta', {}).get('aipictures_reference_weight'):
            node['inputs']['weight'] = weight


def finish_output(result, folder, emit, cancel, transparent=False, smoothing=True):
    if not transparent:
        result['output_background'] = 'preserve'
        return result
    from .background import process_result
    return process_result(result, folder, emit, cancel, smoothing)
