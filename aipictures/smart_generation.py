"""Frozen single-image jobs. Secrets and live clients never enter persisted parameters."""
import json
import threading
from dataclasses import fields
from pathlib import Path

from .api_config import AuthEndpoint
from .api_generation import generate_image, no_secret, plan_art
from .engine import Cancelled
from .storage import write_json


def generate(folder: Path, graph: dict, params: dict, planner: AuthEndpoint | None,
             image: AuthEndpoint | None, reference: Path | None, client,
             cancel: threading.Event, emit) -> dict:
    secrets = tuple(auth.key for auth in (planner, image) if auth)
    prompt, negative = params['user_prompt'], params['user_negative']
    def check() -> None:
        if cancel.is_set():
            raise Cancelled('任务已取消；不会继续调用下一阶段。')
    check()
    if not planner and not image and params.get('translation'):
        from .local_translation import translate
        emit('api_stage',{'message':'正在将中文描述翻译为英文，仅使用本地 CPU…'})
        translated = translate(prompt,negative,params['translation'],cancel)
        prompt,negative = translated['positive'],translated['negative']
        check()
        params['effective_translation'] = translated
        write_json(folder/'translation.json',dict(translated,original_positive=params['user_prompt'],
                                                original_negative=params['user_negative']))
    if planner:
        emit('api_stage', {'message':'正在整理画面需求；尚未调用生图模型…'})
        plan, metadata = plan_art(planner, prompt, negative, reference,
            'cloud image' if image else 'local Z-Image Turbo' if params.get('model_family')=='zimage' else 'local SDXL', cancel, secrets)
        prompt, negative = plan.positive_prompt, plan.negative_prompt
        check()
        write_json(folder/'plan.json', {'positive_prompt':prompt,'negative_prompt':negative,
                                       'summary':plan.summary,**metadata})
        emit('art_plan', plan.summary)
    check()
    if image:
        result = generate_image(image, folder, prompt, negative, reference, cancel, emit,
            bool(reference and params.get('reference_policy')=='preserve'))
    else:
        from .workflow import ImageRequest
        from .image_constraints import apply_constraints
        from .prompt_binding import bind_request
        from .lora_catalog import style_prompt
        from .engine_service import release_idle_models
        request = ImageRequest(**{field.name:params[field.name] for field in fields(ImageRequest)})
        prompt,negative=apply_constraints(prompt,negative,params.get('prompt_constraints',{}))
        request.positive, _ = style_prompt(prompt, request.lora)
        request.negative = negative
        if reference and params.get('reference_policy')=='preserve':
            request.positive += ', preserve reference details except for changes explicitly requested'
        reference_name = ''
        if reference and params['bindings']['reference']:
            from PIL import Image, ImageOps
            from .reference_analysis import opaque_reference
            emit('api_stage', {'message':'正在准备参考图；保留原始颜色…'})
            with Image.open(reference) as source:
                rgb = opaque_reference(ImageOps.exif_transpose(source).convert('RGBA'))
            prepared = folder/'reference_rgb.png'
            rgb.save(prepared)
            check()
            reference_name = client.upload_image(prepared)
        check()
        if params.get('model_family')=='zimage':
            from .zimage import prompt_text
            graph=json.loads(json.dumps(graph))
            graph['text']['inputs']['text']=prompt_text(prompt,negative)
            mapping=params['bindings']
        else:
            graph, mapping = bind_request(graph, request, reference_name, params['denoise'],
                preserve_reference=params.get('reference_policy')=='preserve')
        no_secret(json.dumps(graph,ensure_ascii=False),*secrets)
        params.update(positive=request.positive,negative=request.negative,bindings=mapping)
        write_json(folder/'workflow.json',graph)
        emit('workflow_ready', {'graph':graph,'params':params.copy()})
        emit('api_stage', {'message':'方案就绪，正在通过本地 ComfyUI 生成…'})
        result = client.generate(graph,folder,emit,cancel)
        result['inference_cache_release'] = release_idle_models(client)
    check()
    from .general_image import finish_output
    # Cloud returns native pixels. Matting follows generation and never blends frames.
    return finish_output(result,folder,emit,cancel,params['output_background']=='transparent',False)
