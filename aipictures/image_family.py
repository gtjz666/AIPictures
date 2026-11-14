"""Local image-family UI state and snapshots, independent of animation models."""
import json
import secrets
from dataclasses import asdict

from .workflow import ImageRequest
from .storage import write_json
from . import zimage, flux_klein


def effective_family(window, reference=None):
    """Automatic routing is explicit in the engine choice and frozen per job."""
    family = window.model_family.currentData()
    if family == 'auto':
        from .h3_image import settings
        data=getattr(getattr(window,'api_controller',None),'data',None)
        if data and ((window.reference_path if reference is None else reference) or getattr(getattr(window,'reference_chat',None),'extra',{})) and settings(data):return 'h3_image'
        if hasattr(window,'reference_chat') and window.reference_chat.extra:
            return 'flux_klein'
        return 'flux_klein' if (window.reference_path if reference is None else reference) else 'zimage'
    return family


def restore(window):
    if getattr(window, 'family_restored', False): return
    window.family_restored = True
    info = window.info['object_info']
    ready = zimage.available(info)
    flux_ready = flux_klein.enabled(info, window.api_controller.data)
    preferred = 'auto' if ready else 'flux_klein' if flux_ready else 'auto'
    path = window.api_controller.data / 'image-family.json'
    if path.exists():
        try:
            saved = json.loads(path.read_text('utf-8'))
            choice = saved.get('family')
            if saved.get('routing_version') == 2 and choice in ('auto', 'zimage', 'flux_klein','h3_image'):
                preferred = choice
        except (OSError, ValueError): pass
    window.model_family.setCurrentIndex(window.model_family.findData(preferred))
    apply_ui(window)


def apply_ui(window):
    if window.api_controller.cloud: return
    info = getattr(window, 'info', {}).get('object_info', {})
    native = effective_family(window) == 'zimage'
    flux = effective_family(window) == 'flux_klein'
    from .h3_image import settings,canvas
    h3_ready=bool(settings(window.api_controller.data));h3=effective_family(window)=='h3_image'
    referenced = bool(window.reference_path or getattr(getattr(window,'reference_chat',None),'extra',{}))
    for choice, ready in (
        ('auto', h3_ready or flux_klein.enabled(info, window.api_controller.data) if referenced else zimage.available(info)),
        ('zimage', (zimage.reference_available if referenced else zimage.available)(info)),
        ('flux_klein', flux_klein.enabled(info, window.api_controller.data)),('h3_image',h3_ready)):
        index=window.model_family.findData(choice)
        if index>=0:window.model_family.model().item(index).setEnabled(ready)
    previous = getattr(window, 'active_image_family', None)
    current = effective_family(window)
    if current != previous:
        window.steps.setValue(6 if h3 else 9 if native else 4)
        window.cfg.setValue(1.)
        window.sampler.setCurrentText('euler'); window.scheduler.setCurrentText('simple')
        if native: window.denoise.setValue(getattr(window, 'zimage_denoise', .45))
        window.active_image_family = current
        for control in (window.width,window.height):control.setMaximum(8192 if h3 else 2048);control.setSingleStep(32 if h3 else 64)
        if h3:
            refs=window.reference_chat.references() if hasattr(window,'reference_chat') else {}
            from PIL import Image,ImageOps
            if refs:
                with Image.open(next(iter(refs.values()))) as im:width,height=ImageOps.exif_transpose(im).size
            else:width,height=1,1
            width,height=canvas(width,height);window.width.setValue(width);window.height.setValue(height)
    window.model.hide(); window.model_label.hide()
    for name in ('lora', 'lora_category', 'strength', 'steps', 'cfg', 'sampler', 'scheduler',
                 'reference_strength', 'denoise', 'quality_mode'):
        getattr(window, name).setEnabled(False)
    window.image_form.setRowVisible(window.quality_mode, False)
    window.image_form.setRowVisible(window.denoise, native and referenced)
    window.denoise.setEnabled(native and referenced)
    window.translate_prompt.hide(); window.reference_policy.hide(); window.reference_policy_label.hide()
    window.workflow_selector.setEnabled(window.connected and not window.preparing)
    if h3:
        window.context_label.setText('H3 · 原生参考编辑' if referenced else 'H3 · 文字生图')
        window.reference_note.setText('编号最小的参考图作为编辑基础；用图号指定其他图片的用途。原生图片条件，不经过全图外观转写。')
        window.model_note.setText('MiniMax H3 Image · 6步 · 最多16图。约400万像素起，保留基础图比例；手指、遮挡与身份细节仍需检查。')
    elif flux:
        window.context_label.setText('FLUX · 参考编辑' if referenced else 'FLUX · 图片创作')
        window.reference_note.setText('参考图提供角色与布局，提示词描述目标画风和改动。未要求改变的细节尽量保留；仍需检查输出。')
        window.model_note.setText('当前使用 FLUX.2 Klein · 4步 · 独立参考条件，重新生成目标画面。')
    else:
        window.context_label.setText('Z-Image · 小幅重绘' if referenced else 'Z-Image · 中文创作')
        window.reference_note.setText('原图小幅重绘适合局部外观调整；换风格或视角请选自动路线或FLUX。' if referenced else
                                      '无参考图时直接按文字生成；自动路线添加参考图后使用FLUX。')
        window.model_note.setText('当前使用 Z-Image Turbo · 9步 · 原生中文。' + ('重绘幅度越高，角色细节越容易改变。' if referenced else ''))
    if window.custom_graph is not None:
        window.model_note.setText('导入工作流保留在高级编辑器；请将“后台预设”切回“自动选择”，使用当前图片路线。')
    from .ui_hints import tip
    window.denoise.setToolTip(tip('只影响Z-Image小幅重绘：低值接近原图，高值容易改变角色。换风格优先使用自动路线。'))
    window.style_status.setText('反向内容为软性排除要求；不是独立负向引导。')
    if window.generation_type.currentData() != 'walk':
        ready = h3_ready if h3 else (zimage.reference_available(info) if referenced else zimage.available(info)) if native else flux_klein.enabled(info, window.api_controller.data)
        window.generate_button.setEnabled((h3 or window.connected) and ready and not window.preparing)
        if window.connected and not ready:
            window.model_note.setText('当前路线的模型或验证记录缺失，请连接已配置的后端或手动选择可用引擎；不会切回SDXL。')
    if hasattr(window,'workbench'):
        window.workbench.refresh_reference()
        if hasattr(window.workbench,'update_generation_page'):window.workbench.update_generation_page()


def snapshot(window, reference_name=''):
    if window.custom_graph is not None:raise ValueError('Z-Image 使用独立自动工作流，请把“后台预设”恢复为“自动选择”。')
    seed=int(window.seed.text())
    if seed==-1:seed=secrets.randbelow(2**53)
    if not 0<=seed<2**64:raise ValueError('种子范围应为 0–2^64-1，或 -1 随机。')
    from .prompt_language import texts
    visible,visible_negative=window.positive.toPlainText(),window.negative.toPlainText()
    positive,negative=texts(window)
    request=ImageRequest(zimage.UNET,positive,negative,window.width.value(),window.height.value(),9,1.,seed,'euler','simple')
    denoise=window.denoise.value() if reference_name else 1.
    graph,mapping=zimage.build(request,window.info['object_info'],reference_name,denoise)
    params=asdict(request)
    params.update(mode='chat',model_family='zimage',user_prompt=visible,user_negative=visible_negative,
        prompt_language='chinese_display_english_request',
        image_route=window.model_family.currentData(),template='Z-Image Turbo · 参考重绘' if reference_name else 'Z-Image Turbo · 文字生图',
        bindings=mapping,denoise=denoise,reference_policy='img2img' if reference_name else 'none',reference_strength=None if reference_name else 0.,
        reference_preprocessing='contain_pad_rgb' if reference_name else None,
        output_background=window.output_background.currentData(),intent={'unmatched':''},negative_unmatched='',
        lora_style=None,quality_mode='off',edge_smoothing=False,negative_policy='positive_text_constraints_cfg1')
    return graph,params


def save_selection(window):
    write_json(window.api_controller.data/'image-family.json',{'family':window.model_family.currentData(),'routing_version':2})


def remember_denoise(window, value):
    if window.model_family.currentData()=='zimage':window.zimage_denoise=value


def use_reference_route(window, *, imported=False) -> None:
    # Automatic is a visible choice, not an invisible replacement of a manual engine.
    if window.api_controller.cloud: return
    if imported:
        window.add_chat('软件', '导入工作流仅供高级编辑；SDXL正常生成路线已退役，原文件保留。')
    apply_ui(window)


def reference_snapshot(window, reference_name):
    from . import reference_edit
    seed=int(window.seed.text())
    if seed==-1:seed=secrets.randbelow(2**53)
    if not 0<=seed<2**64:raise ValueError('种子范围应为0–2^64-1，或-1随机。')
    from .prompt_language import texts
    visible,visible_negative=window.positive.toPlainText(),window.negative.toPlainText()
    positive,negative=texts(window)
    request=ImageRequest(reference_edit.MODEL,positive,negative,
        max(256,round(window.width.value()/16)*16),max(256,round(window.height.value()/16)*16),40,4.,seed,'euler','simple')
    graph,mapping=reference_edit.build(request,reference_name,window.info['object_info'])
    params=asdict(request)
    params.update(mode='chat',model_family='qwen_edit',user_prompt=visible,user_negative=visible_negative,
        prompt_language='chinese_display_english_request',
        template='Qwen-Image-Edit 2511',bindings=mapping,denoise=1.,reference_policy='semantic',
        reference_strength=None,output_background=window.output_background.currentData(),
        intent={'unmatched':''},negative_unmatched='',lora_style=None,quality_mode='off',edge_smoothing=False)
    return graph,params


def flux_snapshot(window, reference_name=''):
    if not flux_klein.enabled(window.info['object_info'],window.api_controller.data):
        raise ValueError('FLUX.2 Klein 尚未通过本机生成验证，请使用已验证的图片引擎。')
    if window.custom_graph is not None:
        raise ValueError('FLUX使用独立自动工作流，请把“后台预设”切回“自动选择”。')
    seed=int(window.seed.text())
    if seed==-1:seed=secrets.randbelow(2**53)
    from .prompt_language import texts
    visible,visible_negative=window.positive.toPlainText(),window.negative.toPlainText()
    positive,negative=texts(window)
    request=ImageRequest(flux_klein.UNET,positive,negative,window.width.value(),window.height.value(),4,1.,seed,'euler','flux2')
    graph,mapping=flux_klein.build(request,window.info['object_info'],reference_name)
    params=asdict(request)
    params.update(mode='chat',model_family='flux_klein',user_prompt=visible,user_negative=visible_negative,
        prompt_language='chinese_display_english_request',
        image_route=window.model_family.currentData(),template='FLUX.2 Klein 4B',bindings=mapping,denoise=1.,
        reference_policy='semantic' if reference_name else 'none',reference_strength=None,
        output_background=window.output_background.currentData(),intent={'unmatched':''},negative_unmatched='',
        lora_style=None,quality_mode='off',edge_smoothing=False,negative_policy='positive_text_constraints_cfg1')
    return graph,params
