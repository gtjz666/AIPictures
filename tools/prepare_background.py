"""Install approved local foreground weights; existing defaults remain usable."""
import argparse
from pathlib import Path
from aipictures.background import session,model_file,create_session,ALLOWED_MODELS,SETTINGS
from aipictures.storage import write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',choices=ALLOWED_MODELS)
    parser.add_argument('--root'); parser.add_argument('--download',action='store_true')
    parser.add_argument('--activate',action='store_true')
    args=parser.parse_args()
    if args.model:
        if not args.root: parser.error('--root is required when selecting another model')
        root=Path(args.root).resolve()
        create_session(args.model,root,args.download)
        if args.activate: write_json(SETTINGS,{'schema_version':1,'model':args.model,'root':str(root)})
        print('Local foreground model ready:',model_file(args.model,root),flush=True)
        return
    session(allow_download=True)
    print('Local background removal model ready:',model_file(),flush=True)


if __name__=='__main__': main()
