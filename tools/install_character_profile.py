import argparse
from pathlib import Path
from aipictures.character_profile import install_adaptive_profile
from aipictures.engine import ComfyClient

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('reference')
    parser.add_argument('--url', default='http://127.0.0.1:8188')
    parser.add_argument('--title',default='侧视人物参考')
    args = parser.parse_args()
    result = install_adaptive_profile(args.reference,ComfyClient(args.url),args.title)
    print(Path(result['reference']).parent/'profile.json')
