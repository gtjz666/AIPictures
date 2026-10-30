from PIL import Image
from tools.export_chat_gifs import looping_preview


def test_one_shot_preview_only_changes_loop_extension(tmp_path):
    frames=[Image.new('RGBA',(12,16),(n*40,80,120,255)) for n in range(3)]
    source=tmp_path/'jump.gif';target=tmp_path/'preview.gif'
    frames[0].save(source,save_all=True,append_images=frames[1:],duration=[100,120,140],disposal=2)
    original=source.read_bytes();report=looping_preview(source,target)
    assert source.read_bytes()==original and report['frames']==3
    assert report['pixels_and_timing_exact'] and not report['resampled']
    with Image.open(source) as gif:assert 'loop' not in gif.info
    with Image.open(target) as gif:assert gif.info['loop']==0
