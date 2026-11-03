"""Real local multimodal recognition; no diffusion job and no user window termination."""
import argparse
import json
import threading
from pathlib import Path

from aipictures.local_intent import analyze, settings
from aipictures.storage import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--motion', type=Path)
    parser.add_argument('--brief', required=True)
    parser.add_argument('--kind', choices=['image', 'animation'], default='image')
    parser.add_argument('--negative', default='水印，文字，重复主体')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('输出已有记录，请选择新目录。')
    config = settings(args.data, require_validated=False)
    if not config:
        raise ValueError('请先完成 setup_local_intent。')
    result = analyze(config, args.brief, args.negative, args.reference, args.motion, args.output,
                     threading.Event(), lambda kind, data: print(data.get('message', kind), flush=True), selected_kind=args.kind)
    print(json.dumps(result['plan'], ensure_ascii=False, indent=2), flush=True)
    write_json(args.output/'probe.json', dict(route=result['route'], ready=result['status']=='ready',
                                             engine_released=result['engine_released']))


if __name__ == '__main__':
    main()
