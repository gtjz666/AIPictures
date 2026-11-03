"""Enable the optional reference route only after a completed and visually reviewed run."""
import argparse
import json
from pathlib import Path
from aipictures.storage import DATA,write_json
from aipictures.workflow_library import digest


def register(config_path:Path,result:Path,data:Path=DATA)->dict:
    config=json.loads(config_path.read_text('utf-8'))
    manifest=json.loads(result.read_text('utf-8'));folder=result.parent
    review=json.loads((folder/'visual-review.json').read_text('utf-8'))
    if not review.get('passed'):raise ValueError('参考动作/主体保真尚未通过目视检查，不能开放此路线。')
    if manifest.get('status')!='completed' or manifest.get('source_result',{}).get('backend')!='ComfyUI/H3-Ref2VA':
        raise ValueError('请选择专用Ref2VA真实完成的video.json。')
    source=Path(manifest['source_video'])
    if not source.is_file() or digest(source)!=manifest['source_sha256']:raise ValueError('完整动画缺失或已被修改。')
    paths=[folder/row['image'] for row in manifest.get('frames',[])]
    if len(paths)<5 or [digest(p) for p in paths]!=manifest['source_result']['frame_sha256']:
        raise ValueError('生成帧缺失或已修改，请先检查原任务。')
    command_path=folder/'native-command.json'
    if manifest['source_result'].get('staged'):command_path=folder/'native_sample/native-command.json'
    command=json.loads(command_path.read_text('utf-8'))
    graph=json.loads((folder/'workflow.json').read_text('utf-8'))
    actual=graph['references']['inputs']
    if (config['width'],config['height'])!=(actual['width'],actual['height']):raise ValueError('配置分辨率未经过本次验收。')
    if Path(command['command'][0]).resolve()!=Path(config['python']).resolve():raise ValueError('验收结果不是此独立环境生成的。')
    if Path(command['cwd']).resolve()!=Path(config['source']).resolve():raise ValueError('验收源码路径不一致。')
    for row in config['models']:
        path=Path(row['path'])
        if path.stat().st_size!=row['bytes'] or digest(path)!=row['sha256']:raise ValueError('模型发布SHA核验失败，保留文件供检查。')
    config.update(validated=True,validation_manifest=str(result.resolve()),validation_video_sha256=manifest['source_sha256'],visual_review=review)
    write_json(data/'motion-native-settings.json',config);return config


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--result',type=Path,required=True);p.add_argument('--data',type=Path,default=DATA)
    a=p.parse_args();register(a.config,a.result,a.data);print('动作参考引擎已注册，重新启动软件可使用。')


if __name__=='__main__':main()
