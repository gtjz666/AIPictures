"""Explicit geometry/identity bindings and the trained FLUX 4B depth adapter."""
import json,re,subprocess,sys
from pathlib import Path
from .engine import Cancelled
from .storage import write_json

ADAPTER='flux2_klein_4b_refcontrol_depth.safetensors'

def resolve(brief,references,choice='auto'):
    from .professional_prompt import labels,style_transfer
    ids=set(map(int,references));text=labels(brief)
    if choice=='off':return None
    if not ids:
        if choice!='auto':raise ValueError('结构参考图尚未添加。')
        return None
    replacement=re.search(r'将\s*图(\d+)([^，。；\n]{0,60}?)(?:替换(?:为|成)|更换(?:为|成)|换成)\s*图(\d+)',text)
    target=None;source=None
    style_only=bool(replacement and re.match(r'(?:的|中的)?(?:美术)?(?:风格|画风|材质)',text[replacement.end():]))
    if replacement and not re.search('风格|画风',replacement[2]) and not style_only:source,target=int(replacement[1]),int(replacement[3])
    if choice!='auto':source=int(choice);target=None
    elif style_only:return None
    elif style_transfer(brief):return None  # Preserve the existing, separately validated style-only route.
    elif source is None and re.search('采用|参考|沿用|保持|保留|按照|照着|跟随|匹配|模仿|摆出|作出|提供|复刻|复制',text):
        matches=set(map(int,re.findall(r'图(\d+)[^图，。；\n]{0,18}?(?:姿势|姿态|动作|结构|构图)',text)))
        if len(matches)==1:source=matches.pop()
        elif len(ids)==1 and re.search('保持|保留|沿用',text) and re.search('姿势|姿态|构图|结构',text):source=next(iter(ids))
    if source is None:return None
    if source not in ids:raise ValueError('结构参考图尚未添加。')
    if target is None:
        others=ids-{source}
        if len(others)>1:raise ValueError('结构优先需要明确的一张主体图；请保留主体图与结构图后再生成。')
        target=next(iter(others)) if others else source
    if target not in ids:raise ValueError('主体参考图尚未添加。')
    if ids-{source,target}:raise ValueError('结构优先当前支持一张结构图与一张主体图，不会忽略其他图片。')
    return dict(structure=source,identity=target,method='trained_depth_4b',anatomy_assumed=False)

def settings(data):
    try:
        value=json.loads((Path(data)/'structure-control-settings.json').read_text('utf-8'))
        if value.get('validated') is not True or any(not Path(value[k]).exists() for k in ('python','weights','aux_source')):return None
        return value
    except (OSError,KeyError,ValueError,TypeError):return None

def build(request,info,uploads,binding,config):
    from .multi_reference import build as references_graph
    if not config or not config.get('validated'):raise ValueError('结构控制尚未通过本机验证，未提交普通参考生成。')
    adapter=config.get('adapter',ADAPTER)
    strength=config.get('strength',.9)
    if adapter!=ADAPTER or not isinstance(strength,(int,float)) or not .8<=strength<=1.:raise ValueError('结构适配组件设置与已验证流程不符。')
    if adapter not in info.get('LoraLoaderModelOnly',{}).get('input',{}).get('required',{}).get('lora_name',[[]])[0]:raise ValueError('结构适配组件缺失，请刷新连接。')
    from dataclasses import replace
    source,target=binding['structure'],binding['identity']
    from .multi_reference import LABEL,NUMBERS
    def remap(text):
        def label(match):
            v=match.group(1) or match.group(2);n=NUMBERS[v] if v in NUMBERS else int(v)
            if n not in (source,target):raise ValueError('提示词引用了结构流程之外的图片。')
            return 'Image '+str(2 if n==target else 1)
        return LABEL.sub(label,text)
    # Model-input numbering is private and independent of gallery slot numbering.
    ordered={1:'__structure_depth__',2:uploads[target]}
    graph,mapping=references_graph(replace(request,positive='refcontrol. Image 1 provides geometry only. Image 2 provides subject identity and appearance. '+remap(request.positive),negative=remap(request.negative)),info,ordered)
    graph['structure_adapter']=dict(class_type='LoraLoaderModelOnly',inputs=dict(model=['model',0],lora_name=adapter,strength_model=strength))
    graph['release' if 'release' in graph else 'guider']['inputs']['model']=['structure_adapter',0]
    mapping.update(reference=['image_1','image_2'],structural_binding=binding,model_inputs=[dict(node='image_1',gallery_number=source,role='depth_geometry'),dict(node='image_2',gallery_number=target,role='identity_rgb')])
    mapping.pop('numbered_references',None)
    return graph,mapping

def extract(config,source,output,width,height,cancel,emit):
    from .owned_process import OwnedProcessJob
    output=Path(output);request=output.with_suffix('.request.json');log=output.with_suffix('.log')
    if cancel.is_set():raise Cancelled('结构提取已取消。')
    write_json(request,dict(source=str(source),output=str(output),weights=config['weights'],aux_source=config['aux_source'],width=width,height=height))
    emit('intent_stage',dict(message='正在提取参考结构…'))
    owner=None
    with log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen([config['python'],'-u',str(Path(__file__).with_name('structure_worker.py')),str(request)],stdout=stream,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        try:
            owner=OwnedProcessJob(process.pid)
            while process.poll() is None:
                if cancel.wait(.15):raise Cancelled('结构提取已取消。')
        finally:
            if owner:owner.close()
            if process.poll() is None:process.terminate();process.wait(timeout=15)
    if process.returncode:raise ValueError('结构提取失败，请查看本次结构日志；未使用普通参考替代。')
    if cancel.is_set():raise Cancelled('结构提取已取消。')
    value=json.loads((output/'structure.json').read_text('utf-8'));value['worker_returncode']=process.returncode
    return value
