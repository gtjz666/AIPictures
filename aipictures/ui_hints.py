"""Short, local hover help; no inference, network requests or automatic choices."""
import html
from PySide6.QtCore import Qt


def tip(text):
    return '<table width="260" cellspacing="0" cellpadding="0"><tr><td>'+html.escape(text).replace('\n','<br>')+'</td></tr></table>'


def install_hints(w):
    descriptions={
        'generation_type':'选择单张图片或连续动画；动画类型由此决定，不需要在提示词重复写“动画”。',
        'animation_action':'选择待机、走路、跑步、跳跃或下蹲。下蹲与跳跃保留完整终点；动作由选择决定，无需在提示词中重复。',
        'animation_engine':'完整骨骼动作把整段姿态序列直接送入模型；自动适配即可生成，手调为可选。',
        'motion_mode':'自动适配按当前参考图生成完整动作；手动方式使用你保存的逐帧关节调整。',
        'animation_source':'参考图沿用已有角色；仅文字会先绘制角色，再生成动作。生成读取原图颜色，完成后再抠透明背景；骨骼分析使用独立副本。',
        'animation_steps':'动画推理次数。默认 20；增加会更慢，不保证外观更准确。',
        'animation_detail':'原生细节直接生成 768×1024，并使用更密的连续姿态输入，耗时更长。快速预览采用 480×640 和较少姿态输入，再放大到导出尺寸。两者都保留原始帧。',
        'animation_sampler':'手动选择动画采样器。固定 seed 后可以比较两种方式；采样选择不会分析提示词或自动切换 LoRA。',
        'animation_color':'默认保留生成原色，不再逐区域改写皮肤和服装 RGB。参考校色可能改变渐变与线稿，适合主动进行配色对照。两种方式都保留模型原始帧。',
        'walk_count':'从连续动画选出 8 或 16 张帧。16 帧播放更细，但不保证动作更准确。',
        'walk_fps':'每秒播放的帧数。数值越大，播放越快。',
        'workflow_selector':'自动工作流支持人物、物件和场景，不按关键词套入人体骨骼。手动导入预设时沿用其结构。',
        'model':'用于单张图片与文字动画的角色图；连续动画使用独立的 Wan 模型。',
        'width':'单张图片输出宽度；参考图建议保持原比例。动画画布固定。',
        'height':'单张图片输出高度；参考图建议保持原比例。动画画布固定。',
        'denoise':'数值越小越接近参考原图，越大越容易改变外观。保留细节模式最高 0.25。',
        'reference_policy':'按描述创作使用新画布，可修改视角与姿势。原图小幅修改沿用原构图，重绘最高 0.25。动画单独保留自己的策略。',
        'reference_strength':'自动单图工作流的图像参考比重，0 为仅文字；越高越接近原图，也越难改变视角。导入的自定义工作流请在高级编辑器调整对应节点。',
        'output_background':'完整画面保留场景和背景；透明主体在生成完成后才执行本地去背景。动画同样先生成完整帧，再导出透明帧，原始生成图保留。',
        'quality_mode':'高清修复会重新推测纹理。保留参考细节时使用标准平滑，避免改画细节。',
        'steps':'图像推理次数。默认 24；增加会更慢，不保证质量持续提高。',
        'cfg':'提示词影响程度。太高可能使颜色和轮廓失真，通常先用 6.5。',
        'seed':'-1 每次随机；固定一个数字便于比较参数变化。相同种子也不能保证跨工作流一致。',
        'sampler':'图像去噪算法。通常保留 dpmpp_2m。',
        'scheduler':'安排各步去噪强度。通常保留 karras。',
        'lora_category':'只筛选下方风格列表。你手动选择具体 LoRA 后才生效，不分析提示词选风格。',
        'lora':'手动选择画风。不使用 LoRA 会保留基础模型风格；参考图保留模式不叠加风格。',
        'strength':'所选 LoRA 的影响强度。推荐值因模型而异，过高可能失真。',
        'url':'本机 ComfyUI 地址，默认 http://127.0.0.1:8188。',
        'connect_button':'连接已经运行的 ComfyUI，并刷新可用模型列表。',
        'start_engine_button':'启动已有的本地 ComfyUI，等待就绪后连接；不重新下载模型。',
        'reconnect_button':'本地引擎未启动时启动它，再恢复连接。失败任务不会自动重跑。',
        'unload_button':'仅引擎空闲时释放模型显存；下一次生成需要重新加载。',
        'positive':'描述人物、物件、场景、画风、姿势和视角。自动工作流不会预填或暗中加入侧视、单人等限制。SDXL 不认识的中文仍保留原文。',
        'negative':'填写不希望出现的内容。动画会把常见排除项整理成生成要求；不能保证完全排除缺陷。',
        'generate_button':'按当前设置加入本地生成队列；结果先保存为缓存。',
        'cancel_button':'只取消本软件当前任务；已生成的文件保留。',
    }
    for name,text in descriptions.items():
        control=getattr(w,name); control.setToolTip(tip(text)); control.setToolTipDuration(12000)
    for key,text in {
        'creation':'选择生成类型、动画方式、角色来源和播放设置。',
        'image':'调整基础模型、尺寸、参考图策略和画质。',
        'sampling':'调整采样参数，并手动筛选、选择风格 LoRA。',
        'connection':'查看引擎连接、启动本地 ComfyUI 和释放空闲显存。',
    }.items(): w.settings_buttons[key].setToolTip(tip(text))
    item_hints={
        'reference_policy':['按描述创作新构图，参考图用于外观条件；可手动选择 LoRA。','沿用原构图进行小幅修改；不叠加风格 LoRA。AI 仍可能改变细节。'],
        'quality_mode':['只平滑透明边缘和显示缩放，不生成额外纹理。','适合动漫线条；可能重画纹理，耗时增加。','适合照片；可能重画皮肤和材质，耗时增加。'],
        'generation_type':['绘制一张图片，可使用文字或参考图。','按所选动作生成连续帧，可预览并导出精灵图和 GIF。'],
        'animation_engine':['输入完整的逐帧姿态序列，自动适配或手动调整均可。'],
        'animation_source':['请主动添加参考图；不会自动使用历史角色图。','无需参考图；先按外观描述生成角色，再制作动作。'],
    }
    for name,texts in item_hints.items():
        combo=getattr(w,name)
        for index,text in enumerate(texts): combo.setItemData(index,tip(text),Qt.ItemDataRole.ToolTipRole)
