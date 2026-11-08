import threading
import json
from unittest.mock import patch
from aipictures.motion_prompt import compile_prompt,generated_constraints,QUALITY_NEGATIVE
import pytest


def test_generated_motion_constraints_do_not_lock_a_still_portrait():
    positive='紫发绿眼少女，发髻垂发，表情平静，白色无袖衬衫，黑色过膝袜。固定机位，全身构图。'
    clean,negative=generated_constraints(positive,'依据已提供素材制作动画，外观与动作各按其参考用途。','')
    assert '紫发绿眼少女' in clean and '白色无袖衬衫' in clean and '黑色过膝袜' in clean
    assert '表情平静' not in clean and '固定机位' not in clean and '全身构图' not in clean
    assert negative==QUALITY_NEGATIVE and '重复帧' not in negative and '机位' not in negative


def test_explicit_user_requests_are_not_filtered():
    text='紫发少女，表情平静，固定机位，全身构图。'
    clean,negative=generated_constraints(text,'表情平静，固定机位，全身构图','禁止重复帧，非固定机位')
    assert '表情平静' in clean and '固定机位' in clean and '全身构图' in clean
    assert negative.endswith('\n禁止重复帧，非固定机位')


def test_generated_cleanup_preserves_emotion_requests_and_clothing_graphics():
    clean,_=generated_constraints('蓝发少女，微笑，白色微笑图案衬衫。','她看起来开心','')
    assert '微笑' in clean and '白色微笑图案衬衫' in clean
    clean,_=generated_constraints('蓝发少女，表情平静，白色微笑图案衬衫。','替换参考人物','')
    assert '表情平静' not in clean and '白色微笑图案衬衫' in clean


def test_reference_editing_context_has_explicit_retention_roles_not_guessed_actions():
    user='保留绿色眼睛。\n1.000–2.000秒：右手向上。'
    prompt=compile_prompt(user,True)
    assert '[video editing + reference generation]' in prompt
    assert 'attribute_transfer' in prompt and 'fully_preserved' in prompt and '[Shot 1]' in prompt
    assert 'neutral standing introduction' in prompt and 'feet, legs, hips, torso' in prompt
    assert user in prompt and prompt.count(user)==1
    assert '<Picture 1>' not in compile_prompt('黄色机器人',False)


def test_real_prompt_planner_cannot_add_camera_exclusions_for_motion(tmp_path):
    from aipictures.local_intent import analyze
    source=tmp_path/'source.gif';source.write_bytes(b'no motion captioning or decoding')
    class Session:
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def complete(self,*args,**kwargs):
            return json.dumps(dict(kind='animation',summary='替换角色',positive_prompt='紫发少女，表情平静。',
                negative_prompt='重复帧、非固定机位、非全身构图',timeline=[],observations=[],questions=[])),{}
    with patch('aipictures.intent_observation.observe') as observe:
        result=analyze({},'替换人物，动作按参考','保留用户排除项',None,source,tmp_path/'job',threading.Event(),
            selected_kind='animation',session_factory=Session)
        observe.assert_not_called()
    plan=result['plan']
    assert '紫发少女' in plan['positive_prompt'] and '表情平静' not in plan['positive_prompt']
    assert plan['negative_prompt']==QUALITY_NEGATIVE+'\n保留用户排除项'
    assert not plan['timeline']


def test_probe_preparation_preserves_seed_sources_and_does_not_generate(tmp_path,monkeypatch):
    from tools.probe_motion_fidelity import main
    baseline=tmp_path/'baseline';baseline.mkdir()
    image=baseline/'reference.png';image.write_bytes(b'original-image-bytes')
    source=baseline/'source.gif';source.write_bytes(b'original-motion-bytes')
    params=dict(reference=str(image),motion_reference=str(source),seconds=8.,seed=611683140949314,
        prompt='紫发少女，表情平静。',negative='非固定机位、重复帧')
    (baseline/'video.json').write_text(json.dumps(dict(status='completed',params=params)),encoding='utf-8')
    (baseline/'intent-plan.json').write_text(json.dumps(dict(plan=dict(positive_prompt=params['prompt'],negative_prompt=params['negative']),
        request=dict(brief='替换为图片人物',negative='不要文字'))),encoding='utf-8')
    target=tmp_path/'candidate'
    monkeypatch.setattr('sys.argv',['probe','--baseline',str(baseline),'--folder',str(target),'--seconds','4'])
    with patch('aipictures.video_generation.generate') as generate:
        main();generate.assert_not_called()
    job=json.loads((target/'job.json').read_text('utf-8'))
    assert job['status']=='prepared' and job['params']['seed']==params['seed']
    assert (target/'reference.png').read_bytes()==image.read_bytes()
    assert (target/'motion_reference.gif').read_bytes()==source.read_bytes()
    assert '表情平静' not in job['params']['prompt'] and job['params']['negative'].endswith('不要文字')
    assert json.loads((target/'comparison.json').read_text('utf-8'))['exact_duration_ab'] is False
    # Re-running cannot overwrite existing evidence or submit a duplicate job.
    with pytest.raises(FileExistsError):main()


def test_custom_reference_usage_remains_an_explicit_requirement(tmp_path):
    from aipictures.local_intent import analyze
    from PIL import Image
    image=tmp_path/'image.png';Image.new('RGB',(16,24),'blue').save(image)
    source=tmp_path/'source.gif';source.write_bytes(b'not decoded by assistant')
    class Session:
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def complete(self,*args,**kwargs):
            return json.dumps(dict(kind='animation',summary='替换角色',positive_prompt='蓝发少女，表情平静，全身构图，固定机位。',
                negative_prompt='重复帧',timeline=[],observations=[],questions=[])),{}
    with patch('aipictures.intent_observation.observe',return_value=dict(appearance=dict(reference_use='custom',style='动漫'))):
        result=analyze({},'根据素材生成动画','',image,source,tmp_path/'job',threading.Event(),
            selected_kind='animation',role='custom',reference_usage='全身构图，固定机位，表情平静',session_factory=Session)
    assert '表情平静' in result['plan']['positive_prompt'] and '全身构图' in result['plan']['positive_prompt']


def test_probe_refuses_to_filter_manually_edited_baseline(tmp_path,monkeypatch):
    from tools.probe_motion_fidelity import main
    baseline=tmp_path/'baseline';baseline.mkdir()
    (baseline/'video.json').write_text(json.dumps(dict(status='completed',params=dict(prompt='用户修改过',negative=''))))
    (baseline/'intent-plan.json').write_text(json.dumps(dict(plan=dict(positive_prompt='原自动词',negative_prompt=''))))
    target=tmp_path/'candidate'
    monkeypatch.setattr('sys.argv',['probe','--baseline',str(baseline),'--folder',str(target)])
    with pytest.raises(SystemExit):main()
    assert not target.exists()
