"""User-facing inference stages, shared by all explicitly selected animation types."""

NODE_LABELS = {
    'UNETLoader': '加载动作模型', 'CLIPLoader': '加载文字编码器',
    'CLIPTextEncode': '编码动作描述', 'CLIPVisionLoader': '加载参考编码器',
    'CLIPVisionEncode': '编码参考外观', 'VAELoader': '加载图像编码器',
    'LoadImage': '读取参考与骨骼', 'ImageBatch': '准备连续骨骼',
    'WanAnimateToVideo': '编码参考与连续骨骼（采样前）',
    'KSampler': '动作采样', 'TrimVideoLatent': '整理动作数据',
    'SaveLatent': '保存动作数据', 'LoadLatent': '读取已保存动作',
    'VAEDecode': '解码原生动画帧', 'SaveImage': '保存动画图片',
}


def monitor_text(event: str, data: dict, graph: dict | None = None) -> str | None:
    if event in ('monitor_waiting', 'cancel_pending'):
        return data.get('message', '继续检查同一生成任务…')
    if event == 'executing' and data.get('node') is not None:
        node = str(data['node'])
        return NODE_LABELS.get((graph or {}).get(node, {}).get('class_type'), '处理动画节点…')
    if event == 'monitor_status':
        state = data.get('state')
        if state == 'cancelling': return '正在等待后端确认取消…'
        if state == 'queued': return '等待共享引擎执行当前任务…'
        if state == 'downloading': return '下载已生成的动画图片…'
        if state == 'running': return NODE_LABELS.get(data.get('node_type'), '后端正在处理当前动作…')
        return '正在核对当前任务记录…'
    return None
