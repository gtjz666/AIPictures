import argparse
from pathlib import Path
import threading
from aipictures.video_frames import extract_video


def main():
    parser=argparse.ArgumentParser(description='本地视频转独立 PNG / 精灵图，不混帧。')
    parser.add_argument('video',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--frames',type=int,choices=(0,8,16),default=8,help='0保留全部源帧（最多240张），并沿用源FPS。')
    parser.add_argument('--fps',type=int,default=8);parser.add_argument('--loop',action='store_true')
    parser.add_argument('--transparent',action='store_true')
    parser.add_argument('--sampling',choices=('uniform','keyframes'),default='keyframes')
    a=parser.parse_args()
    print(extract_video(a.video,a.output,a.frames,a.fps,a.loop,a.transparent,threading.Event(),lambda k,d:print(k,d),sampling=a.sampling))


if __name__=='__main__':main()
