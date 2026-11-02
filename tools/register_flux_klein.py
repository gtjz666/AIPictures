"""Register Klein after completed text AND reference probes have been viewed."""
import argparse
import json
from pathlib import Path

from PIL import Image

from aipictures import flux_klein
from aipictures.storage import DATA, write_json
from aipictures.workflow_library import digest


def verify(path: Path, reference: bool) -> dict:
    path=Path(path).resolve()
    result=json.loads(path.read_text('utf-8'))
    history=result.get('history',{})
    prompt=history.get('prompt')
    if not isinstance(prompt,list) or len(prompt)<3 or not isinstance(prompt[2],dict):
        raise ValueError('验收记录缺少后端执行的工作流。')
    graph=prompt[2]
    status=history.get('status',{})
    if status.get('status_str')!='success' or not status.get('completed'):
        raise ValueError('请提供后端已成功完成的result.json。')
    if (graph.get('model',{}).get('inputs',{}).get('unet_name','').replace('\\','/').split('/')[-1]!=flux_klein.UNET or
        graph.get('clip',{}).get('inputs',{}).get('type')!='flux2' or
        graph.get('sigmas',{}).get('inputs',{}).get('steps')!=4 or
        ('reference' in graph)!=reference):
        raise ValueError('验收工作流不属于本软件的FLUX四步文字/参考路线。')
    images=result.get('images',[]);checksums=result.get('image_sha256',[])
    if not images or len(images)!=len(checksums):
        raise ValueError('验收图像或哈希记录不完整。')
    for raw,sha in zip(images,checksums):
        image=Path(raw)
        if not image.is_absolute():image=path.parent/image.name
        if not image.is_file() or digest(image)!=sha:
            raise ValueError('验收图片缺失或已改变，保持当前设置不变。')
        with Image.open(image) as im:
            im.load()
            if min(im.size)<256:raise ValueError('请提供实际尺寸的生成结果。')
    return {'result':str(path),'result_sha256':digest(path),'image_sha256':checksums,
            'prompt_id':result['prompt_id']}


def register(text_result: Path, reference_result: Path, data: Path=DATA) -> dict:
    receipts=[verify(text_result,False),verify(reference_result,True)]
    config={'schema_version':1,'validated':True,'family':'flux_klein',
            'validation_results':receipts,'text_default':'zimage',
            'negative_policy':'natural_language_soft_constraints_cfg1',
            'quality_note':'本机流程已完成；中文角色细节仍有漏执行，不全面替换Z-Image。'}
    write_json(Path(data)/'flux-klein-settings.json',config)
    return config


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--text-result',type=Path,required=True)
    p.add_argument('--reference-result',type=Path,required=True)
    p.add_argument('--data',type=Path,default=DATA)
    a=p.parse_args();register(a.text_result,a.reference_result,a.data)
    print('FLUX已注册；重新连接软件后可用。中文文字创作仍默认Z-Image。')


if __name__=='__main__':main()
