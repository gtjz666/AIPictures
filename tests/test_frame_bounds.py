from PIL import Image, ImageDraw

from aipictures.frame_bounds import canvas_review, boundary_warnings


def test_cut_head_and_empty_frame_are_reported_without_editing_pixels():
    image=Image.new('RGBA',(64,96))
    ImageDraw.Draw(image).rectangle((20,0,43,80),fill=(80,40,120,255))
    before=image.tobytes();review=canvas_review(image)
    assert review['status']=='boundary' and review['margins'][1]==0
    assert '第 4 帧' in boundary_warnings([{'index':3,'canvas_review':review}])[0]
    assert image.tobytes()==before
    empty=canvas_review(Image.new('RGBA',image.size))
    assert empty['status']=='empty'
    assert '没有可见主体' in boundary_warnings([{'index':0,'canvas_review':empty}])[0]


def test_clear_canvas_does_not_flag_faint_background_noise():
    image=Image.new('RGBA',(64,96),(50,60,70,2))
    ImageDraw.Draw(image).rectangle((20,12,43,80),fill=(80,40,120,255))
    review=canvas_review(image)
    assert review['status']=='inside' and review['bbox']==[20,12,44,81]
    assert not boundary_warnings([{'index':0,'canvas_review':review}])
