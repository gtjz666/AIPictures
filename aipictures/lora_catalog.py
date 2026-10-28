"""Style metadata and an explicit SDXL LoRA layer, independent of Qt."""
import json
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent/'resources/lora_catalog.json').read_text('utf-8'))['models']


def entry_for(name):
    name=(name or '').replace('\\','/')
    return next((item for item in catalog() if item['filename']==name),None)


def display_name(name):
    entry=entry_for(name)
    return f'[{entry["category"]} · {entry["title"]}] SDXL' if entry else '[未分类] '+name


def is_sdxl(checkpoint):
    name=checkpoint.lower()
    return bool(re.search(r'sd[_ -]?xl|animagine|illustrious|pony|juggernaut.?xl|dreamshaper.?xl',name))


def validate_selection(name,checkpoint):
    if entry_for(name) and not is_sdxl(checkpoint):
        raise ValueError('此风格 LoRA 适用于 SDXL，请选择 SDXL 基础模型；不能用于 SD1.5 / FLUX / Wan。')


def style_prompt(positive,name):
    entry=entry_for(name)
    if not entry: return positive,None
    phrases=entry['triggers']+entry.get('conditioning',[])
    added=[word for word in phrases if word.casefold() not in positive.casefold()]
    positive=', '.join(added+[positive]) if added else positive
    return positive,{'id':entry['id'],'category':entry['category'],'title':entry['title'],
        'base_family':entry['base_family'],'added_style_phrases':added,'source':entry['source']}


def bind_lora(graph,name,strength,checkpoint):
    """Replace only our layer, before adapters and existing author-defined LoRAs."""
    owned=[key for key,node in graph.items() if node.get('_meta',{}).get('aipictures_lora')]
    for key in owned:
        inputs=graph[key]['inputs']; replacements={0:inputs['model'],1:inputs['clip']}
        for other,node in graph.items():
            if other==key: continue
            for field,value in node['inputs'].items():
                if isinstance(value,list) and len(value)==2 and str(value[0])==key and value[1] in replacements:
                    node['inputs'][field]=replacements[value[1]][:]
        del graph[key]
    if not name: return
    validate_selection(name,checkpoint)
    checkpoints=[key for key,node in graph.items() if node['class_type']=='CheckpointLoaderSimple']
    if len(checkpoints)!=1:
        raise ValueError('此工作流有多组基础模型，不能自动判断 LoRA 目标，请在高级工作流中配置。')
    base=checkpoints[0]; key='aipictures_style_lora'
    if key in graph: raise ValueError('工作流节点命名冲突，请在高级工作流中重命名 aipictures_style_lora。')
    for node in graph.values():
        for field,value in node['inputs'].items():
            if isinstance(value,list) and len(value)==2 and str(value[0])==base and value[1] in (0,1):
                node['inputs'][field]=[key,value[1]]
    graph[key]={'class_type':'LoraLoader','inputs':{'model':[base,0],'clip':[base,1],
        'lora_name':name,'strength_model':strength,'strength_clip':strength},
        '_meta':{'title':'所选风格 LoRA','aipictures_lora':True}}
