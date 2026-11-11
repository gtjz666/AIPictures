"""Remove adapter layers from a working copy while preserving source workflow files."""
from copy import deepcopy


def plain_workflow(graph: dict, *, trained_structure=False) -> dict:
    if trained_structure and 'structure_adapter' not in graph:raise ValueError('结构适配组件未接入，未提交生成。')
    result=deepcopy(graph)
    for key in list(result):
        node=result[key];kind=node['class_type']
        # Only the built-in, validated geometric route may retain this adapter.
        # Legacy style/speed adapters and imported workflows still get bypassed.
        if trained_structure and key=='structure_adapter':
            from .structure_control import ADAPTER
            if (kind!='LoraLoaderModelOnly' or node['inputs'].get('lora_name')!=ADAPTER
                    or node['inputs'].get('model')!=['model',0]
                    or not .8<=node['inputs'].get('strength_model',0)<=1.):
                raise ValueError('结构适配组件与已验证流程不符，未提交生成。')
            continue
        if kind not in ('LoraLoader','LoraLoaderModelOnly'):continue
        replacements={0:node['inputs']['model']}
        if kind=='LoraLoader':replacements[1]=node['inputs']['clip']
        for other in result.values():
            for field,value in other['inputs'].items():
                if isinstance(value,list) and len(value)==2 and str(value[0])==key:
                    if value[1] not in replacements:raise ValueError('旧LoRA节点输出无法自动绕过，请使用自动工作流。')
                    other['inputs'][field]=deepcopy(replacements[value[1]])
        del result[key]
    if any('lora' in node['class_type'].lower() for key,node in result.items() if not (trained_structure and key=='structure_adapter')):
        raise ValueError('旧工作流包含特殊LoRA节点，请恢复自动工作流；原文件保留。')
    return result
