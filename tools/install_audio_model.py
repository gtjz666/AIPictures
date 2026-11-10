"""Install only the pinned ACE-Step instrumental model pack; never start inference."""
import argparse
import json
import sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--engine-root',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    sys.path.insert(0,str(a.source.resolve()))
    from freevideo_engine.image_gen.image_pack import install,catalog,base
    from aipictures.storage import write_json
    rows=catalog()['groups']['music'];last=[None]
    write_json(a.report.with_name('catalog.json'),dict(files=rows,total_bytes=sum(r['bytes'] for r in rows),purpose='standalone instrumental music'))
    def progress(row):
        write_json(a.report,row)
        key=(row.get('file'),row.get('phase'))
        if key!=last[0]:print(json.dumps(row,ensure_ascii=False),flush=True);last[0]=key
    install(a.root,progress,lambda:None,engine_root=a.engine_root,group='music')
    write_json(a.report,dict(status='completed',model_root=str((base(a.root)/'music').resolve())))
    print('AUDIO_MODEL_INSTALLED',flush=True)


if __name__=='__main__':main()
