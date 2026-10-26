import argparse
from aipictures.character_profile import install_profile, PROFILE_FILE
from aipictures.engine import ComfyClient

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('reference')
    parser.add_argument('--url', default='http://127.0.0.1:8188')
    args = parser.parse_args()
    result = install_profile(args.reference, ComfyClient(args.url))
    print(PROFILE_FILE)
