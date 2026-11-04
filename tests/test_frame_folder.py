import json
import threading
from pathlib import Path
import pytest
from PIL import Image
from aipictures.frame_motion_input import folder_frames,import_frames
from aipictures.prompt_timeline import remove_owned_timeline,remove_generated_summary,TITLE


def test_folder_uses_natural_order_and_metadata_fps_without_a_video_decoder(tmp_path,monkeypatch):
    import av
    for i in (10,2,1):Image.new('RGBA',(20,30),(i,20,30,255)).save(tmp_path/f'frame_{i}.png')
    (tmp_path/'sprite_sheet.json').write_text(json.dumps(dict(fps=29.97)))
    paths,fps=folder_frames(tmp_path);owned=tmp_path/'owned';owned.mkdir()
    monkeypatch.setattr(av,'open',lambda *_a,**_k:pytest.fail('A frame folder must not decode a source video'))
    source,meta=import_frames(paths,fps,owned,threading.Event())
    mapping=json.loads((owned/'source-map.json').read_text('utf-8'))
    assert [r['source'] for r in mapping]==['frame_1.png','frame_2.png','frame_10.png']
    assert meta['duration']==pytest.approx(3/29.97)
    assert json.loads(source.read_text('utf-8'))['fps']==29.97


def test_folder_reads_nested_exported_frames_and_refuses_escaping_paths(tmp_path):
    (tmp_path/'frames').mkdir()
    for i in (1,2):Image.new('RGBA',(20,30),'red').save(tmp_path/'frames'/f'{i}.png')
    manifest=tmp_path/'source.json'
    data=dict(fps=12,frames=[dict(image=f'frames/{i}.png') for i in (1,2)])
    manifest.write_text(json.dumps(data));paths,fps=folder_frames(tmp_path)
    assert fps==12 and all(p.parent==tmp_path/'frames' for p in paths)
    data['frames'][0]['image']='../outside.png';manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='相对PNG'):folder_frames(tmp_path)


def test_empty_folder_has_actionable_error_and_default_fps(tmp_path):
    with pytest.raises(ValueError,match='至少需要2张'):folder_frames(tmp_path)
    for i in (1,2):Image.new('RGBA',(20,30),'red').save(tmp_path/f'{i}.png')
    assert folder_frames(tmp_path)[1]==24


def test_only_generated_timing_summary_is_removed_and_untimed_constraints_survive():
    rows=[dict(start=0,end=.5,description='抬手')]
    original='紫发人物，白衣。\n从0秒开始：抬手(0.0s)→收手(0.5s)\n保持水彩风格。'
    assert remove_generated_summary(original,rows)=='紫发人物，白衣。\n保持水彩风格。'
    assert remove_generated_summary(original,[])==original
    footer='\n\n'+TITLE+'\n时间为参考素材秒数；按选定起点播放，启用循环时按此顺序重复。\n0.000–0.500秒：抬手'
    assert remove_owned_timeline('白衣。'+footer+footer+'\n\n保留柔光。')=='白衣。\n\n保留柔光。'
