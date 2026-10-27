"""Download the public IS-Net model once; later image processing is offline."""
from aipictures.background import session,model_file


def main():
    session(allow_download=True)
    print('Local background removal model ready:',model_file(),flush=True)


if __name__=='__main__': main()
