"""Loop actual generated GIFs for chat display; retain original one-shot exports and pixel bytes."""
import argparse
from pathlib import Path
import shutil
from PIL import Image
from aipictures.animation_actions import ACTIONS
from aipictures.storage import write_json
from aipictures.workflow_library import digest


def looping_preview(source: Path, target: Path) -> dict:
    source,target=Path(source),Path(target)
    if source.resolve()==target.resolve() or target.exists():
        raise ValueError('演示 GIF 必须使用新的输出位置，不能覆盖原始动画。')
    original=source.read_bytes()
    with Image.open(source) as image:
        if image.format!='GIF':raise ValueError('输入必须是 GIF。')
        loop=image.info.get('loop')
    if loop not in (None,0):raise ValueError('本工具只接收单次或无限循环的 GIF。')
    if loop is None:
        # Insert an application extension after the global color table. Image
        # descriptors, graphic control extensions, palettes and LZW data stay exact.
        offset=13+(3*(2**((original[10]&7)+1)) if original[10]&128 else 0)
        extension=b'\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00'
        output=b'GIF89a'+original[6:offset]+extension+original[offset:]
    else:output=original
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(output)
    with Image.open(source) as before,Image.open(target) as after:
        assert after.info.get('loop')==0 and before.n_frames==after.n_frames
        count=before.n_frames
        for index in range(count):
            before.seek(index);after.seek(index)
            assert before.convert('RGBA').tobytes()==after.convert('RGBA').tobytes()
            assert before.info.get('duration')==after.info.get('duration')
    assert source.read_bytes()==original
    return {'source':str(source.resolve()),'preview':str(target.resolve()),'frames':count,
            'source_sha256':digest(source),'pixels_and_timing_exact':True,'resampled':False,
            'original_loop':loop,'preview_loop':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--actions',nargs='+',choices=ACTIONS,default=list(ACTIONS))
    args=p.parse_args();records=[]
    for action in args.actions:
        records.append(looping_preview(args.root/action/(action+'.gif'),args.out/(action+'.gif')))
    write_json(args.out/'report.json',{'records':records,'note':'演示仅改变循环标记，正式单次动画保留。'})


if __name__=='__main__':main()
