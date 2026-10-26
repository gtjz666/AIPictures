from dataclasses import dataclass, asdict


@dataclass
class ImageRequest:
    checkpoint: str
    positive: str
    negative: str = 'blurry, watermark, text'
    width: int = 768
    height: int = 768
    steps: int = 24
    cfg: float = 6.5
    seed: int = 1
    sampler: str = 'euler'
    scheduler: str = 'normal'
    lora: str = ''
    lora_strength: float = 0.8


def build_workflow(r: ImageRequest):
    if not r.checkpoint or not r.positive.strip():
        raise ValueError('请选择模型并输入提示词')
    if any(v < 64 or v > 2048 or v % 8 for v in (r.width, r.height)):
        raise ValueError('尺寸应在 64–2048 之间且为 8 的倍数')
    model, clip = ['1', 0], ['1', 1]
    graph = {'1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': r.checkpoint}}}
    if r.lora:
        graph['8'] = {'class_type': 'LoraLoader', 'inputs': {'model': model, 'clip': clip,
            'lora_name': r.lora, 'strength_model': r.lora_strength, 'strength_clip': r.lora_strength}}
        model, clip = ['8', 0], ['8', 1]
    graph.update({
        '2': {'class_type': 'CLIPTextEncode', 'inputs': {'text': r.positive, 'clip': clip}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': r.negative, 'clip': clip}},
        '4': {'class_type': 'EmptyLatentImage', 'inputs': {'width': r.width, 'height': r.height, 'batch_size': 1}},
        '5': {'class_type': 'KSampler', 'inputs': {'seed': r.seed, 'steps': r.steps, 'cfg': r.cfg,
            'sampler_name': r.sampler, 'scheduler': r.scheduler, 'denoise': 1.0,
            'model': model, 'positive': ['2', 0], 'negative': ['3', 0], 'latent_image': ['4', 0]}},
        '6': {'class_type': 'VAEDecode', 'inputs': {'samples': ['5', 0], 'vae': ['1', 2]}},
        '7': {'class_type': 'SaveImage', 'inputs': {'images': ['6', 0], 'filename_prefix': 'AIPictures/image'}}})
    return graph
