"""Official four-step FLUX.2 Klein graph, using the existing Qwen3 encoder.

Reference conditioning is separate from the output latent: a side view need not
remain a side view. No SDXL adapter, pose map, translation model or LoRA is used.
"""
from .workflow import ImageRequest
from .zimage import _name, prompt_text
import json
from pathlib import Path

UNET = 'flux-2-klein-4b.safetensors'
ENCODER = 'qwen_3_4b_fp8_mixed.safetensors'
VAE = 'flux2-vae.safetensors'
NODES = ('EmptyFlux2LatentImage', 'Flux2Scheduler', 'SamplerCustomAdvanced',
         'CFGGuider', 'RandomNoise', 'KSamplerSelect', 'ReferenceLatent',
         'VAEEncode', 'ConditioningZeroOut', 'ImageScaleToTotalPixels')


def enabled(info: dict, data: Path) -> bool:
    """A downloaded model is not a passed real generation test."""
    try:
        return available(info) and json.loads((Path(data) / 'flux-klein-settings.json').read_text('utf-8')).get('validated') is True
    except (OSError, ValueError):
        return False


def available(info: dict) -> bool:
    try:
        for node, field, file in (('UNETLoader', 'unet_name', UNET),
                                  ('CLIPLoader', 'clip_name', ENCODER),
                                  ('VAELoader', 'vae_name', VAE)):
            _name(info, node, field, file)
        return all(n in info for n in NODES)
    except ValueError:
        return False


def build(request: ImageRequest, info: dict, reference: str = '') -> tuple[dict, dict]:
    if request.lora:
        raise ValueError('FLUX.2 Klein 不使用 SDXL LoRA。')
    if not available(info):
        raise ValueError('FLUX.2 Klein 组件或节点不完整，请安装组件并刷新连接。')
    if any(n < 256 or n > 2048 or n % 16 for n in (request.width, request.height)):
        raise ValueError('FLUX 画布须为256–2048像素，且为16的整数倍。')
    if not 0 <= request.seed < 2**64:
        raise ValueError('请使用有效的实际种子。')
    text = prompt_text(request.positive, request.negative)
    graph = {
        'model': {'class_type': 'UNETLoader', 'inputs': {
            'unet_name': _name(info, 'UNETLoader', 'unet_name', UNET), 'weight_dtype': 'default'}},
        'clip': {'class_type': 'CLIPLoader', 'inputs': {
            'clip_name': _name(info, 'CLIPLoader', 'clip_name', ENCODER), 'type': 'flux2', 'device': 'default'}},
        'vae': {'class_type': 'VAELoader', 'inputs': {'vae_name': _name(info, 'VAELoader', 'vae_name', VAE)}},
        'text': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['clip', 0], 'text': text}},
        'negative': {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['text', 0]}},
        'latent': {'class_type': 'EmptyFlux2LatentImage', 'inputs': {
            'width': request.width, 'height': request.height, 'batch_size': 1}},
        'noise': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': request.seed}},
        'sigmas': {'class_type': 'Flux2Scheduler', 'inputs': {
            'steps': 4, 'width': request.width, 'height': request.height}},
        'sampler': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
        'guider': {'class_type': 'CFGGuider', 'inputs': {
            'model': ['model', 0], 'positive': ['text', 0], 'negative': ['negative', 0], 'cfg': 1.}},
        'sample': {'class_type': 'SamplerCustomAdvanced', 'inputs': {
            'noise': ['noise', 0], 'guider': ['guider', 0], 'sampler': ['sampler', 0],
            'sigmas': ['sigmas', 0], 'latent_image': ['latent', 0]}},
        'decode': {'class_type': 'VAEDecode', 'inputs': {'samples': ['sample', 0], 'vae': ['vae', 0]}},
        'save': {'class_type': 'SaveImage', 'inputs': {
            'images': ['decode', 0], 'filename_prefix': 'AIPictures/flux_klein'}},
    }
    positive = ['text', 0]
    if reference:
        graph.update({
            'reference': {'class_type': 'LoadImage', 'inputs': {'image': reference}},
            'ref_scale': {'class_type': 'ImageScaleToTotalPixels', 'inputs': {
                'image': ['reference', 0], 'upscale_method': 'nearest-exact', 'megapixels': 1., 'resolution_steps': 1}},
            'ref_encode': {'class_type': 'VAEEncode', 'inputs': {
                'pixels': ['ref_scale', 0], 'vae': ['vae', 0]}},
            'pos_ref': {'class_type': 'ReferenceLatent', 'inputs': {
                'conditioning': ['text', 0], 'latent': ['ref_encode', 0]}},
            'neg_ref': {'class_type': 'ReferenceLatent', 'inputs': {
                'conditioning': ['negative', 0], 'latent': ['ref_encode', 0]}},
        })
        positive = ['pos_ref', 0]
        graph['guider']['inputs'].update(positive=positive, negative=['neg_ref', 0])
    if 'AIPicturesReleaseCompletedEncoders' in info:
        graph['release'] = {'class_type': 'AIPicturesReleaseCompletedEncoders', 'inputs': {
            'model': ['model', 0], 'conditioning': positive}}
        graph['guider']['inputs']['model'] = ['release', 0]
    return graph, {'positive': [('text', 'text')], 'negative': [],
                   'reference': ['reference'] if reference else [], 'sampler': 'sample'}
