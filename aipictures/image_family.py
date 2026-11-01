"""Local image-family UI state and snapshots, independent of animation models."""
import json
import secrets
from dataclasses import asdict

from .workflow import ImageRequest
from .storage import write_json
from . import zimage


def restore(window):
    if getattr(window,'family_restored',False):return
    window.family_restored=True
    ready=zimage.available(window.info['object_info'])
    window.model_family.model().item(1).setEnabled(ready)
    preferred='zimage' if ready else 'sdxl'
    path=window.api_controller.data/'image-family.json'
    if path.exists():
        try:preferred=json.loads(path.read_text('utf-8')).get('family',preferred)
        except (OSError,ValueError):pass
    if preferred=='zimage' and not ready:preferred='sdxl'
    index=window.model_family.findData(preferred)
    if index>=0:window.model_family.setCurrentIndex(index)


def apply_ui(window):
    native=window.model_family.currentData()=='zimage' and window.generation_type.currentData()!='walk'
    if window.api_controller.cloud:return
    window.model_family.model().item(1).setEnabled(
        zimage.available(getattr(window,'info',{}).get('object_info',{})) and not window.reference_path)
    previous=getattr(window,'active_image_family','sdxl')
    current='zimage' if native else 'sdxl'
    if current!=previous:
        if native:
            window.sdxl_sampling=(window.steps.value(),window.cfg.value(),window.sampler.currentText(),window.scheduler.currentText())
            window.steps.setValue(9);window.cfg.setValue(1.)
            window.sampler.setCurrentText('euler');window.scheduler.setCurrentText('simple')
        elif hasattr(window,'sdxl_sampling'):
            steps,cfg,sampler,scheduler=window.sdxl_sampling
            window.steps.setValue(steps);window.cfg.setValue(cfg)
            window.sampler.setCurrentText(sampler);window.scheduler.setCurrentText(scheduler)
        window.active_image_family=current
    window.model.setVisible(not native);window.model_label.setVisible(not native)
    if native:
        for name in ('lora','lora_category','strength','steps','cfg','sampler','scheduler','reference_strength','denoise','quality_mode'):
            getattr(window,name).setEnabled(False)
        # Keep the automatic-preset choice reachable if an imported SDXL graph was active.
        window.workflow_selector.setEnabled(window.connected and not window.preparing)
        window.translate_prompt.hide()
        window.reference_policy.hide();window.reference_policy_label.hide()
        window.context_label.setText('Z-Image · 中文创作')
        window.reference_note.setText('此引擎当前支持无参考图；参考编辑请在“模型与画面”切换 SDXL，或使用云端图片 API。')
        window.model_note.setText('Z-Image 原生理解中英文，9 步生成。当前支持无参考图；参考编辑和 SDXL 风格 LoRA 请切换 SDXL。反向词会转为文字排除要求。')
        if window.custom_graph is not None:
            window.model_note.setText('当前绑定了其他工作流；请将“后台预设”设为“自动选择”，再使用 Z-Image。原工作流文件保留。')
        window.style_status.setText('Z-Image · 原生中文 · 不混接 SDXL LoRA · 反向内容为软性文字约束')
    else:
        window.model_note.setText('SDXL 用于单张图片与文字动画的角色图，可手动选择风格 LoRA；动画使用独立模型。')


def snapshot(window, reference_name=''):
    if reference_name:raise ValueError('Z-Image 当前是文字生图路线；参考图编辑请切换 SDXL 或云端图片 API。')
    if window.custom_graph is not None:raise ValueError('Z-Image 使用独立自动工作流，请恢复自动工作流或切回 SDXL。')
    seed=int(window.seed.text())
    if seed==-1:seed=secrets.randbelow(2**53)
    if not 0<=seed<2**64:raise ValueError('种子范围应为 0–2^64-1，或 -1 随机。')
    positive,negative=window.positive.toPlainText(),window.negative.toPlainText()
    request=ImageRequest(zimage.UNET,positive,negative,window.width.value(),window.height.value(),9,1.,seed,'euler','simple')
    graph,mapping=zimage.build(request,window.info['object_info'])
    params=asdict(request)
    params.update(mode='chat',model_family='zimage',user_prompt=positive,user_negative=negative,
        template='Z-Image Turbo · 中文直出',bindings=mapping,denoise=1.,reference_policy='none',reference_strength=0.,
        output_background=window.output_background.currentData(),intent={'unmatched':''},negative_unmatched='',
        lora_style=None,quality_mode='off',edge_smoothing=False,negative_policy='positive_text_constraints_cfg1')
    return graph,params


def save_selection(window):
    write_json(window.api_controller.data/'image-family.json',{'family':window.model_family.currentData()})


def use_reference_route(window) -> None:
    """A reference or imported SDXL graph needs the supported editor, visibly."""
    if window.api_controller.cloud or window.model_family.currentData()!='zimage':
        return
    window.model_family.setCurrentIndex(window.model_family.findData('sdxl'))
    window.add_chat('软件','已切换 SDXL 参考 / 工作流路线；Z-Image 当前用于无参考图创作。')
