"""Run the unmodified author's inference on closed-line BasicPBC research samples."""
import runpy
import shutil
import sys
from pathlib import Path

import torch
import yaml


def main():
    vendor=Path('D:/ComfyResearch/reference-color')
    root=Path('data/reference-fill-research/native-control').resolve()
    source=vendor/'BasicPBC/dataset/test/laughing_girl'
    case=root/'laughing_girl'
    for sub in ('line','ref/line','ref/gt'): (case/sub).mkdir(parents=True,exist_ok=True)
    for name in ('0000.png','0001.png','0002.png','0003.png'):
        shutil.copy2(source/'line'/name,case/'line'/name)
    for sub in ('gt','line'): shutil.copy2(source/sub/'0000.png',case/'ref'/sub/'0000.png')
    config=yaml.safe_load((vendor/'DACoN/configs/inference.yaml').read_text())
    config['num_gpu']=0; config['datasets']['val']['num_worker']=0; config['val']['save_json']=True
    path=root/'config.yaml'; path.write_text(yaml.safe_dump(config))
    sys.path[:0]=[str(vendor/'DACoN/dacon'),str(vendor/'dinov2')]
    from dinov2.hub.backbones import dinov2_vitl14
    def local_dino(*args,**kwargs):
        model=dinov2_vitl14(pretrained=False)
        model.load_state_dict(torch.load('D:/ComfyModels/reference-color/dinov2_vitl14_pretrain.pth',map_location='cpu',weights_only=True),strict=True)
        return model
    torch.hub.load=local_dino
    torch.set_num_threads(4)
    sys.argv=['inference.py','--config',str(path),'--data',str(root),
        '--model','D:/ComfyModels/reference-color/dacon_v1_1.pth','--version','1_1']
    runpy.run_path(str(vendor/'DACoN/dacon/inference.py'),run_name='__main__')


if __name__=='__main__':main()
