from PIL import Image
from aipictures.pose_sequence import pack_poses
from aipictures.pose_animation import video_workflow


def test_lossless_pages_keep_duplicates_order_and_full_pixel_values(tmp_path):
    frames=[]
    for i in range(9):
        path=tmp_path/f'pose_{i:03}.png'
        image=Image.new('RGB',(32,48),(10 if i<4 else i,85,170));image.putpixel((8,9),(153,51,102))
        image.save(path);frames.append(path)
    target=tmp_path/'poses.tiff';report=pack_poses(frames,target)
    assert report['frames']==9 and report['rgb_pixel_exact'] and not report['frames_blended']
    with Image.open(target) as batch:
        assert batch.n_frames==9
        for i,path in enumerate(frames):
            batch.seek(i)
            with Image.open(path) as source:assert batch.convert('RGB').tobytes()==source.tobytes()


def test_native_graph_loads_one_batch_instead_of_caching_batch_tree():
    graph=video_workflow('ref',['poses.tiff'],'walk','',42,pose_count=33)
    assert graph['8']['inputs']['length']==33
    assert graph['8']['inputs']['pose_video']==['pose_image_0',0]
    assert graph['pose_image_0']['inputs']['image']=='poses.tiff'
    assert not any(n['class_type']=='ImageBatch' for n in graph.values())
