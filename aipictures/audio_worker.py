"""Gated dedicated audio worker; no GUI or video model is loaded."""
import json
import os
import sys
from pathlib import Path


def main():
    value=json.loads(Path(sys.argv[1]).read_text('utf-8'))
    if sys.stdin.readline().strip()!='go':raise SystemExit('Audio worker was not admitted')
    os.environ['FREEVIDEO_HOME']=value['engine_root'];sys.path.insert(0,value['source'])
    from freevideo_engine.locking import runtime_lock
    from freevideo_engine.music.worker import main as generate
    with runtime_lock(Path(value['engine_root'])/'engine.lock',inherit=False,wait_seconds=0):
        code=generate(['--root',value['model_root'],'--out',value['out'],'--caption',value['caption'],
            '--seconds',str(value['seconds']),'--seed',str(value['seed']),'--mode','auto','--device','cuda'])
    raise SystemExit(code)


if __name__=='__main__':main()
