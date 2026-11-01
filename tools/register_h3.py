"""Register a separately installed H3 engine only after a real completed generation."""
import argparse
import json
from pathlib import Path

from aipictures.storage import DATA,write_json
from aipictures.workflow_library import digest


def register(root: Path,result: Path,data: Path=DATA) -> dict:
    root=Path(root).resolve();result=Path(result).resolve()
    machine=json.loads((root/'machine.json').read_text('utf-8'))
    if not machine.get('ready'):raise ValueError('独立环境尚未完成安装，请先检查安装日志。')
    config={**machine,'encoder_root':machine['comfy_root'],'validated':True,'width':768,'height':1024}
    for key in ('python','source','cache','base','checkpoint','encoder_root','vdn_root','model_paths'):
        if not Path(config[key]).exists():raise ValueError('安装记录中的路径不存在：'+key)
    manifest=json.loads(result.read_text('utf-8'))
    source=Path(manifest.get('source_video',''))
    if (manifest.get('status')!='completed' or manifest.get('kind')!='video' or
        manifest.get('source_result',{}).get('backend')!='FreeVideo/VDN-H3' or
        not source.is_file() or digest(source)!=manifest.get('source_sha256')):
        raise ValueError('请提供此引擎真实完成、来源哈希相符的 video.json；安装探测不等于生成验收。')
    frames=manifest.get('frames',[])
    if len(frames)<2 or any(not (result.parent/row['image']).is_file() for row in frames):
        raise ValueError('完整动画预览帧缺失，请先完成解码。')
    command=json.loads((result.parent/'h3-command.json').read_text('utf-8'))['command']
    if Path(command[0]).resolve()!=Path(config['python']).resolve():raise ValueError('验收结果不属于此环境。')
    config.update(validation_manifest=str(result),validation_video_sha256=manifest['source_sha256'],
                  engine_source_commit='518b9843c99ae57c8391706406260130f45eaa5c')
    write_json(Path(data)/'h3-settings.json',config)
    return config


def main():
    parser=argparse.ArgumentParser(description='用真实输出注册可选的独立 H3 引擎，不下载权重。')
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True,help='本软件生成的已完成video.json')
    parser.add_argument('--data',type=Path,default=DATA)
    args=parser.parse_args();register(args.root,args.result,args.data)
    print('H3 已注册。重新打开软件，在“角色与生成”中选择动画模型。')


if __name__=='__main__':main()
