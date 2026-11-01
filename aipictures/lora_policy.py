"""Remove adapter layers from a working copy while preserving source workflow files."""
from copy import deepcopy


def plain_workflow(graph: dict) -> dict:
    result=deepcopy(graph)
    for key in list(result):
        node=result[key];kind=node['class_type']
        if kind not in ('LoraLoader','LoraLoaderModelOnly'):continue
        replacements={0:node['inputs']['model']}
        if kind=='LoraLoader':replacements[1]=node['inputs']['clip']
        for other in result.values():
            for field,value in other['inputs'].items():
                if isinstance(value,list) and len(value)==2 and str(value[0])==key:
                    if value[1] not in replacements:raise ValueError('旧LoRA节点输出无法自动绕过，请使用自动工作流。')
                    other['inputs'][field]=deepcopy(replacements[value[1]])
        del result[key]
    if any('lora' in node['class_type'].lower() for node in result.values()):
        raise ValueError('旧工作流包含特殊LoRA节点，请恢复自动工作流；原文件保留。')
    return result
