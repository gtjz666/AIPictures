"""Local workflow catalog and conservative dependency checks for imported UI graphs."""
import hashlib
import json
from pathlib import Path

from .storage import DATA

CATALOG = DATA / 'workflows' / 'library.json'
MODEL_WIDGETS = {
    'CheckpointLoaderSimple': 'ckpt_name',
    'ControlNetLoader': 'control_net_name',
    'CLIPVisionLoader': 'clip_name',
    'IPAdapterModelLoader': 'ipadapter_file',
    'LoraLoader': 'lora_name',
    'UNETLoader': 'unet_name',
    'VAELoader': 'vae_name',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def list_workflows():
    if not CATALOG.exists():
        return []
    doc = json.loads(CATALOG.read_text('utf-8'))
    if doc.get('schema_version') != 1 or not isinstance(doc.get('workflows'), list):
        raise ValueError('工作流目录索引格式无效')
    return doc['workflows']


def workflow_path(entry):
    path = (DATA / entry['ui_path']).resolve()
    if not path.is_relative_to(DATA.resolve()):
        raise ValueError('工作流路径不在本软件数据目录中')
    return path


def inspect_workflow(graph, object_info):
    """Check the exact installed node/model/input lists, without silently replacing values."""
    nodes = graph.get('nodes')
    if not isinstance(nodes, list):
        raise ValueError('需要 ComfyUI UI 格式工作流')
    ids = [node['id'] for node in nodes]
    problems = []
    if len(set(ids)) != len(ids):
        problems.append('节点 ID 重复')
    node_ids = set(ids)
    for link in graph.get('links', []):
        source = link[1] if isinstance(link, list) else link.get('origin_id')
        target = link[3] if isinstance(link, list) else link.get('target_id')
        if source not in node_ids or target not in node_ids:
            problems.append('连线引用了不存在的节点')
    missing_models, missing_images, missing_nodes = [], [], []
    for node in nodes:
        kind = node['type']
        if kind not in object_info:
            missing_nodes.append(kind)
            continue
        values = node.get('widgets_values', [])
        if not isinstance(values, list) or not values:
            continue
        field = MODEL_WIDGETS.get(kind)
        if kind == 'LoadImage':
            field = 'image'
        if field:
            spec = object_info[kind].get('input', {}).get('required', {}).get(field)
            if spec and isinstance(spec[0], list) and values[0] not in spec[0]:
                if kind == 'LoadImage':
                    missing_images.append(values[0])
                else:
                    missing_models.append(values[0])
        if kind == 'IPAdapterUnifiedLoader' and values[0] == 'PLUS (high strength)':
            spec = object_info.get('IPAdapterModelLoader', {}).get('input', {}).get('required', {}).get('ipadapter_file', [[]])
            if not any('ip-adapter-plus_sdxl_vit-h' in name.lower() for name in spec[0]):
                missing_models.append('IP-Adapter PLUS SDXL ViT-H')
    return {'missing_nodes': sorted(set(missing_nodes)), 'missing_models': sorted(set(missing_models)),
            'missing_images': sorted(set(missing_images)), 'structural_errors': problems,
            'dependencies_ready': not any((missing_nodes, missing_models, missing_images, problems))}


def dependency_summary(report):
    parts = []
    for key, label in [('structural_errors', '结构问题'), ('missing_nodes', '缺少节点'),
                       ('missing_models', '缺少模型'), ('missing_images', '缺少输入图')]:
        if report.get(key):
            parts.append(label + '：' + '、'.join(report[key]))
    return '；'.join(parts) or '基础依赖已齐全；实际出图以测试结果为准。'
