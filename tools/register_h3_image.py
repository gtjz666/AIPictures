"""Register an existing H3 Image installation only after actual desktop jobs pass."""
import argparse
import json
import threading
from pathlib import Path
from PIL import Image
from aipictures.h3_image import PROTOCOL
from aipictures.h3_image_runtime import verify_models
from aipictures.storage import write_json
from aipictures.workflow_library import digest


def register(machine,proof,data):
    config=json.loads(Path(machine).read_text('utf-8'));proof=Path(proof).resolve()
    rows=json.loads((proof/'acceptance.json').read_text('utf-8'))
    counts=[];evidence=[]
    for row in rows:
        if not row.get('actual_qt') or not row.get('actual_models'):raise ValueError('需要实际桌面与模型生成验收。')
        path=Path(row['job']);folder=path.parent;job=json.loads(path.read_text('utf-8'));params=job['params']
        if job['status']!='completed' or params.get('protocol')!=PROTOCOL:raise ValueError('生成任务未成功或协议不匹配。')
        if any(params['h3_image_settings'].get(k)!=config.get(k) for k in ('python','source','source_commit','model_paths','models','encoder')):
            raise ValueError('验收环境与注册配置不同。')
        prompt_ids=[]
        for stage in ('encode','sample','decode'):
            monitor=json.loads((folder/stage/'result/monitor.json').read_text('utf-8'))
            process=json.loads((folder/stage/'process.json').read_text('utf-8'))
            if monitor['state']!='completed' or process['status']!='stopped' or process.get('returncode') is None:raise ValueError('阶段未成功结束。')
            prompt_ids.append(monitor['prompt_id'])
        graph=json.loads((folder/'sample/workflow.json').read_text('utf-8'))['sample']['inputs']
        if (graph['steps'],graph['cfg'],graph['sampler_name'],graph['scheduler'],graph['denoise'])!=(6,1.,'euler','simple',1.):raise ValueError('采样配置不是官方6步路线。')
        encode=json.loads((folder/'encode/workflow.json').read_text('utf-8'))['condition']['inputs']
        count=len([k for k in encode if k.startswith('images.image_')])
        if count!=len(params['references']):raise ValueError('参考图未完整进入编码器。')
        result=json.loads((folder/'result.json').read_text('utf-8'));output=Path(result['images'][0])
        with Image.open(output) as im:
            if im.size!=(params['width'],params['height']):raise ValueError('实际输出尺寸错误。')
        counts.append(count);evidence.append(dict(job=str(path),output=str(output),sha256=digest(output),prompt_ids=prompt_ids,reference_count=count))
    if not counts or 0 not in counts or max(counts)<2:raise ValueError('至少需要真实文字生图与双图编辑各一个完成任务。')
    # Reuse the byte-verified, unchanged weight receipts, never a presence-only flag.
    receipts=json.loads((Path(rows[0]['job']).parent/'model-verification.json').read_text('utf-8'))
    config['verified_models']=receipts
    config['verified_models']=verify_models(config,proof,threading.Event())
    config.update(validated=True,validation=dict(protocol=PROTOCOL,proof=str(proof),cases=evidence,
        scope='Functional native desktop integration; limited visual examples, no universal pose or identity guarantee.'))
    write_json(Path(data)/'h3-image-settings.json',config,durable=True)
    return config['validation']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('machine','proof','data'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(register(a.machine,a.proof,a.data),ensure_ascii=True))


if __name__=='__main__':main()
