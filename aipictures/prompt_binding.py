"""Bind a creation request to an API graph, without changing the template on disk."""
from copy import deepcopy


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[1], int)


def samplers(graph):
    return [(key, node) for key, node in graph.items() if node['class_type'] == 'KSampler']


def single_sampler(graph):
    found = samplers(graph)
    if len(found) != 1:
        raise ValueError('对话绑定目前支持含一个 KSampler 的图像工作流，请在高级编辑器简化或拆分此工作流。')
    return found[0]


def text_targets(graph, link, seen=None):
    seen = set() if seen is None else seen
    if not is_link(link): return []
    key, slot = str(link[0]), link[1]
    if (key, slot) in seen or key not in graph: return []
    seen.add((key, slot))
    node = graph[key]
    kind, inputs = node['class_type'], node['inputs']
    if kind == 'CLIPTextEncode': return [(key, 'text')]
    if kind == 'CLIPTextEncodeSDXL': return [(key, 'text_g'), (key, 'text_l')]
    if kind == 'ControlNetApplyAdvanced':
        return text_targets(graph, inputs.get('positive' if slot == 0 else 'negative'), seen)
    targets = []
    for value in inputs.values():
        if is_link(value): targets.extend(text_targets(graph, value, seen))
    return sorted(set(targets))


def image_sources(graph, link, seen=None):
    seen = set() if seen is None else seen
    if not is_link(link): return []
    key = str(link[0])
    if key in seen or key not in graph: return []
    seen.add(key)
    node = graph[key]
    if node['class_type'] == 'LoadImage': return [key]
    # Do not traverse a VAE/model connection into an unrelated conditioning image.
    sources = []
    for field in ('pixels', 'image', 'images', 'samples', 'latent_image'):
        sources.extend(image_sources(graph, node['inputs'].get(field), seen))
    return sorted(set(sources))


def bindings(graph):
    sampler_id, sampler = single_sampler(graph)
    positive = text_targets(graph, sampler['inputs'].get('positive'))
    negative = text_targets(graph, sampler['inputs'].get('negative'))
    if not positive or not negative or set(positive) & set(negative):
        raise ValueError('无法区分此工作流的正向和负向提示词，请在高级编辑器检查条件连接。')
    if len({key for key, _ in positive}) > 1 or len({key for key, _ in negative}) > 1:
        raise ValueError('此工作流包含多组提示词，需要先在高级编辑器合并输入，避免覆盖独立的风格或区域提示词。')
    references = []
    for node in graph.values():
        if node['class_type'] in ('IPAdapterAdvanced', 'IPAdapter'):
            references.extend(image_sources(graph, node['inputs'].get('image')))
    if not references:
        references = image_sources(graph, sampler['inputs'].get('latent_image'))
    references = sorted(set(references))
    if len(references) > 1:
        raise ValueError('工作流含多张角色参考图，暂不能自动判断上传图片的目标节点。')
    return {'positive': positive, 'negative': negative, 'reference': references, 'sampler': sampler_id}


def add_image_input(graph, name, width, height, strength):
    sampler_id, sampler = single_sampler(graph)
    latent = sampler['inputs'].get('latent_image')
    if not is_link(latent) or graph[str(latent[0])]['class_type'] != 'EmptyLatentImage':
        raise ValueError('此工作流没有可自动转换的空白画布，无法安全添加参考图。')
    decoders = [node for node in graph.values() if node['class_type'] in ('VAEDecode','VAEDecodeTiled')]
    if len(decoders) != 1:
        raise ValueError('此工作流有多组图像解码节点，无法确定参考图使用的 VAE。')
    start = max([int(key) for key in graph if key.isdigit()] + [0]) + 1
    while any(str(start + i) in graph for i in range(3)): start += 3
    load, scale, encode = [str(start + i) for i in range(3)]
    graph[load] = {'class_type': 'LoadImage', 'inputs': {'image': name}, '_meta': {'title': '对话参考图'}}
    graph[scale] = {'class_type': 'ImageScale', 'inputs': {'image': [load, 0], 'upscale_method': 'lanczos',
                    'width': width, 'height': height, 'crop': 'disabled'}}
    graph[encode] = {'class_type': 'VAEEncode', 'inputs': {'pixels': [scale, 0], 'vae': decoders[0]['inputs']['vae']}}
    sampler['inputs']['latent_image'] = [encode, 0]
    sampler['inputs']['denoise'] = strength
    return load


def bind_request(template, request, reference='', denoise=.6, preserve_reference=False):
    graph = deepcopy(template)
    mapping = bindings(graph)
    for key, field in mapping['positive']: graph[key]['inputs'][field] = request.positive
    for key, field in mapping['negative']: graph[key]['inputs'][field] = request.negative
    sampler = graph[mapping['sampler']]['inputs']
    sampler.update(seed=request.seed, steps=request.steps, cfg=request.cfg,
                   sampler_name=request.sampler, scheduler=request.scheduler)
    checkpoints = [node for node in graph.values() if node['class_type'] == 'CheckpointLoaderSimple']
    if len(checkpoints) == 1: checkpoints[0]['inputs']['ckpt_name'] = request.checkpoint
    for node in graph.values():
        if node['class_type'] in ('EmptyLatentImage', 'ImageScale'):
            node['inputs'].update(width=request.width, height=request.height)
    if reference:
        if preserve_reference:
            from .reference_fidelity import effective_denoise
            denoise=effective_denoise(denoise,True)
            if any(node['class_type'].startswith('ControlNetApply') for node in graph.values()):
                raise ValueError('当前工作流带独立姿态控制。优先保留细节请使用自动工作流；改变姿态请选“允许按描述重绘”。')
            if any((node['class_type'].startswith('LoraLoader') and not node.get('_meta',{}).get('aipictures_lora'))
                   or node['class_type']=='ImageUpscaleWithModel' for node in graph.values()):
                raise ValueError('当前预设自带风格 LoRA 或高清重画。优先保留细节请使用自动工作流，或切换“允许按描述重绘”。')
        if not mapping['reference']:
            mapping['reference'] = [add_image_input(graph, reference, request.width, request.height, denoise)]
        else:
            graph[mapping['reference'][0]]['inputs']['image'] = reference
            if image_sources(graph, sampler.get('latent_image')):
                sampler['denoise'] = denoise
                if preserve_reference:
                    for key in image_sources(graph,sampler['latent_image']):
                        graph[key]['inputs']['image']=reference
                        if key not in mapping['reference']: mapping['reference'].append(key)
            elif preserve_reference:
                # IP-Adapter alone supplies identity embeddings, not source image latents.
                mapping['reference'].append(add_image_input(graph,reference,request.width,request.height,denoise))
    from .lora_catalog import bind_lora
    bind_lora(graph,request.lora,request.lora_strength,request.checkpoint)
    return graph, mapping


def check_models(graph, object_info):
    from .workflow_library import MODEL_WIDGETS
    for node in graph.values():
        field = MODEL_WIDGETS.get(node['class_type'])
        if not field: continue
        value = node['inputs'].get(field)
        if is_link(value): continue
        spec = object_info.get(node['class_type'], {}).get('input', {}).get('required', {}).get(field)
        if spec and isinstance(spec[0], list) and value not in spec[0]:
            # Windows ComfyUI enumerates subfolders with backslashes. Catalog and
            # exported workflows use portable slashes; submit the server's exact name.
            canonical=next((item for item in spec[0] if isinstance(item,str) and isinstance(value,str)
                and item.replace('\\','/')==value.replace('\\','/')),None)
            if canonical is not None:
                node['inputs'][field]=canonical
                continue
            raise ValueError('此工作流缺少模型：' + str(value) + '。请补齐权重或选择其他工作流。')
