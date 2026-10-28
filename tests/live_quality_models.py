"""Real local restoration on two cached native frames, without rerunning Wan."""
import threading
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from aipictures.engine import ComfyClient
from aipictures.image_quality import enhance_frames,check_quality_models
from aipictures.storage import DATA,write_json
from aipictures.temporal_animation import release_idle_models


def main():
    client=ComfyClient(); info=client.discover()['object_info']
    sources=[DATA/'animations/20261028_125126_27785417/video/image_001.png',
             DATA/'animations/20261028_123718_6d9c75ca/video/image_012.png']
    root=DATA/'quality-tests'/datetime.now().strftime('%Y%m%d_%H%M%S'); root.mkdir(parents=True)
    previews=Image.new('RGB',(3*384,2*540),'white'); draw=ImageDraw.Draw(previews)
    features=[]
    for row,path in enumerate(sources):
        with Image.open(path) as image:
            features.append(np.asarray(image.resize((32,32)).convert('RGB'),dtype=float))
            previews.paste(image.resize((384,512)),(0,row*540+24))
        draw.text((8,row*540+6),'source',fill='black')
    records=[]
    for col,mode in enumerate(('anime','general'),1):
        check_quality_models(info,mode)
        result=enhance_frames(client,sources,root/mode,mode,lambda *args:None,threading.Event())
        assert len(result['images'])==2
        for row,path in enumerate(result['images']):
            with Image.open(path) as image:
                assert image.size==(768,1024)
                feature=np.asarray(image.resize((32,32)).convert('RGB'),dtype=float)
                distances=[float(np.abs(feature-source).mean()) for source in features]
                assert distances[row]<distances[1-row],distances
                previews.paste(image.resize((384,512)),(col*384,row*540+24))
            draw.text((col*384+8,row*540+6),mode,fill='black')
        records.append({'mode':mode,'prompt_id':result['prompt_id'],'images':result['images'],'order_matches_sources':True})
    release_idle_models(client)
    previews.save(root/'comparison.jpg')
    write_json(DATA/'quality-models-acceptance.json',{'passed':True,'folder':str(root),'tests':records,
        'native_frames_reused':True,'wan_resampled':False,'automatic_model_choice':False})
    print('Both restoration models ran on real cached frames; output order and dimensions passed.',flush=True)


if __name__=='__main__': main()
