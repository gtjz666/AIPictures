import json
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from aipictures.intent_plan import parse_plan, route
from aipictures.intent_media import prepare
from aipictures.local_intent import analyze, LocalSession, settings
from aipictures.engine import Cancelled


def plan(**changes):
    return dict(kind='image', summary='红色药水瓶，俯视', positive_prompt='A red glass potion bottle, top view.',
                negative_prompt='text, watermark', observations=[], timeline=[], questions=[], **changes)


def test_allowlisted_routes_and_ambiguity():
    p = parse_plan(json.dumps(plan()), set())
    assert route(p, reference=False, motion=False) == 'zimage'
    assert route(p, reference=True, motion=False) == 'flux_reference'
    with pytest.raises(ValueError, match='移除动作参考'): route(p, reference=True, motion=True)
    data = plan(); data.update(kind='animation', questions=['请选择主要角色。'])
    with pytest.raises(ValueError, match='请选择主要角色'): route(parse_plan(json.dumps(data), set()), reference=True, motion=True)
    data['questions'] = []
    assert route(parse_plan(json.dumps(data), set()), reference=True, motion=True) == 'h3_reference'


@pytest.mark.parametrize('change', [dict(tool='delete'), dict(observations=[{'asset':'invented','description':'fake'}]),
    dict(timeline=[{'start':0,'end':7,'description':'out of bounds'}]),
    dict(timeline=[{'start':True,'end':1,'description':'bool'}]), dict(positive_prompt=''), dict(questions='yes')])
def test_reject_invalid_or_hallucinated_plan(change):
    data = plan(); data.update(change)
    with pytest.raises(ValueError): parse_plan(json.dumps(data), set(), 1.)


def test_original_gif_timing_and_rgba_not_changed(tmp_path):
    original = tmp_path/'ref.png'; Image.new('RGBA', (160, 220), (243, 241, 240, 0)).save(original)
    images = [Image.new('RGB', (90, 60), (i*40, 10, 30)) for i in range(4)]
    gif = tmp_path/'move.gif'; images[0].save(gif, save_all=True, append_images=images[1:], duration=[30, 80, 40, 100])
    before = original.read_bytes(), gif.read_bytes()
    content, meta = prepare(original, gif, tmp_path/'out', threading.Event(), max_frames=12)
    assert before == (original.read_bytes(), gif.read_bytes())
    assert [round(r['time'], 3) for r in meta['assets'][1]['frames']] == [0, .03, .11, .15]
    assert not meta['temporal_blending'] and meta['sampled_frame_count'] == 4
    assert len([v for v in content if v['type']=='image_url']) == 5


def test_analysis_keeps_negatives_releases_and_asks_before_mode_change(tmp_path):
    state = []
    class Session:
        def __init__(self, *args): pass
        def __enter__(self): state.append('start'); return self
        def __exit__(self, *_): state.append('stop')
        def complete(self, messages):
            assert 'user_request' in messages[1]['content'][0]['text']
            data = plan(); data['kind']='animation'
            return json.dumps(data), {}
    result = analyze({'name':'test'}, '红色瓶子转动', '不能褪色', None, None, tmp_path/'job', threading.Event(), session_factory=Session)
    assert state == ['start','stop'] and result['engine_released']
    assert '不能褪色' in result['plan']['negative_prompt']
    assert result['status']=='needs_input' and result['route'] is None


def test_cancel_before_any_model_or_generation(tmp_path):
    stop = threading.Event(); stop.set()
    class Session:
        def __init__(self, *args): raise Cancelled('cancel')
    with pytest.raises(Cancelled):
        analyze({}, '红色瓶子', '', None, None, tmp_path/'cancel', stop, session_factory=Session)
    assert json.loads((tmp_path/'cancel'/'failure.json').read_text('utf-8'))['status']=='cancelled'


def test_real_private_http_process_and_cancel_cleanup(tmp_path):
    script = tmp_path/'server.py'
    script.write_text('''import json,sys,time
from http.server import HTTPServer,BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'{}')
 def do_POST(self):
  self.rfile.read(int(self.headers['Content-Length']));time.sleep(20)
 def log_message(self,*args):pass
HTTPServer(('127.0.0.1',int(sys.argv[1])),Handler).serve_forever()
''', encoding='utf-8')
    class Session(LocalSession):
        def command(self, port): return [sys.executable, str(script), str(port)]
    cancel = threading.Event(); config={'timeout':30,'max_tokens':256,'server':sys.executable}
    with Session(config, tmp_path/'runtime', cancel, lambda *_: None) as session:
        timer = threading.Timer(.3, cancel.set); timer.start()
        before = time.monotonic()
        with pytest.raises(Cancelled): session.complete([])
        assert time.monotonic()-before < 4
        timer.join()
    assert session.process.poll() is not None


def test_bad_or_unverified_settings_not_enabled(tmp_path):
    (tmp_path/'local-intent-settings.json').write_text('{bad')
    assert settings(tmp_path) is None
    (tmp_path/'local-intent-settings.json').write_text(json.dumps({'schema_version':1,'validated':False}))
    assert settings(tmp_path) is None


def test_perception_keeps_roles_separate_and_checks_frame_order(tmp_path):
    from aipictures.intent_observation import observe
    source=tmp_path/'reference.png';Image.new('RGBA',(60,90),(20,50,100,0)).save(source)
    frames=[Image.new('RGB',(60,90),(i*60,50,100)) for i in range(3)]
    motion=tmp_path/'motion.gif';frames[0].save(motion,save_all=True,append_images=frames[1:],duration=[30,60,90])
    content,evidence=prepare(source,motion,tmp_path/'out',threading.Event())
    class Session:
        bad_order=False
        def complete(self,messages,**kwargs):
            images=[c for c in messages[1]['content'] if c['type']=='image_url']
            if len(images)==1:
                return json.dumps(dict(identity='蓝色角色',clothing_colors='白色衬衣',style='动漫',layout='站立',uncertainties='')),{}
            assert len(images)==3
            rows=[dict(index=i,pose='抬起手臂') for i in range(3)]
            if self.bad_order:rows.reverse()
            return json.dumps(dict(frames=rows,camera='近景',uncertainties='')),{}
    session=Session();result=observe(session,content,evidence,tmp_path/'out')
    assert 'layout' not in result['appearance']
    assert [round(r['time'],3) for r in result['motion']['frames']]==[0,.03,.09]
    assert evidence['assets'][0]['analysis_matte_only']
    session.bad_order=True
    with pytest.raises(ValueError,match='时间或内容不完整'):observe(session,content,evidence,tmp_path/'bad')


def test_species_leak_repaired_without_changing_timing_or_requested_transformation(tmp_path):
    from aipictures.intent_quality import repair_anatomy
    data=plan();data['positive_prompt']='少女前爪抬起'
    data['timeline']=[dict(start=0,end=.5,description='前爪伸展')]
    original=json.dumps(data)
    class Session:
        count=0
        def complete(self,*args,**kwargs):
            self.count+=1
            return json.dumps(dict(positive_prompt='少女屈臂抬手',descriptions=['手臂伸展'])),{}
    session=Session();obs={'appearance':{'identity':'年轻女性'}}
    fixed=json.loads(repair_anatomy(session,original,obs,'模仿参考动作',tmp_path))
    assert fixed['timeline']==[dict(start=0,end=.5,description='手臂伸展')]
    assert fixed['negative_prompt']==data['negative_prompt'] and session.count==1
    assert repair_anatomy(session,original,obs,'变成猫',tmp_path)==original and session.count==1


def test_negative_prompt_never_silently_empty_and_retains_user_words(tmp_path):
    class Session:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def complete(self,messages,**kwargs):
            if kwargs.get('schema'):return json.dumps(dict(positive_prompt='A dreamy glowing object.',negative_prompt='')),{}
            data=plan();data['negative_prompt']='';return json.dumps(data),{}
    result=analyze({'name':'test'},'梦幻模糊光晕的物件','',None,None,tmp_path/'empty',threading.Event(),session_factory=Session)
    assert result['plan']['negative_prompt'] and '模糊' not in result['plan']['negative_prompt']
    result=analyze({'name':'test'},'梦幻光晕','不要文字，保留柔光',None,None,tmp_path/'explicit',threading.Event(),session_factory=Session)
    assert result['plan']['negative_prompt']=='不要文字，保留柔光'


@pytest.mark.parametrize('role,expected',[
    ('appearance',{'identity','clothing_colors','style'}),('style',{'style'}),
    ('custom',{'identity','clothing_colors','style','layout'})])
def test_explicit_reference_purpose_and_custom_use_reach_planner(tmp_path,role,expected):
    source=tmp_path/'ref.png';Image.new('RGB',(60,90),'blue').save(source)
    usage='只参考黑白服装配色和描边，主体换成机器人，不参考发型与站姿' if role=='custom' else ''
    details=[]
    class Session:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def complete(self,messages,**kwargs):
            if kwargs.get('schema',{}).get('required')==['positive_prompt','negative_prompt']:
                return json.dumps(dict(positive_prompt='A robot with black and white clothing and a thin outline.',
                    negative_prompt='text, watermark')),{}
            if kwargs.get('schema'):
                if role=='custom':assert usage in messages[1]['content'][-1]['text']
                return json.dumps(dict(identity='紫发少女',clothing_colors='黑白服装',style='细描边动漫',layout='正面站立',uncertainties='')),{}
            value=json.loads(messages[1]['content'][0]['text']);details.append(value)
            return json.dumps(plan()),{}
    result=analyze({'name':'test'},'画一个机器人','',source,None,tmp_path/'analysis',threading.Event(),
                   role=role,reference_usage=usage,session_factory=Session)
    observation=details[0]['visual_observations']['appearance']
    assert set(observation)-{'uncertainties','reference_use'}==expected
    assert details[0]['reference_roles']==[dict(id='appearance',role=role)]
    assert details[0]['reference_usage']==usage and result['request']['reference_usage']==usage
    assert result['resolved_reference_role']==role and result['engine_released']
    if role=='style':assert '紫发少女' not in json.dumps(observation,ensure_ascii=False)


def test_custom_use_requires_text_before_starting_model(tmp_path):
    with pytest.raises(ValueError,match='自定义用法'):
        analyze({},'创建场景','',tmp_path/'image.png',None,tmp_path/'out',threading.Event(),role='custom')
    assert not (tmp_path/'out').exists()


def test_custom_subject_replacement_is_not_forced_back_to_original_anatomy(tmp_path):
    from aipictures.intent_quality import repair_anatomy
    data=plan();data['positive_prompt']='猫抬起前爪，保留参考的衣物配色'
    original=json.dumps(data)
    class Session:
        def complete(self,*args,**kwargs):raise AssertionError('Custom target was forced back to reference anatomy')
    assert repair_anatomy(Session(),original,{'appearance':{'identity':'少女','reference_use':'custom'}},'替换主体',tmp_path)==original


def test_cross_species_check_includes_timeline_and_front_limbs(tmp_path):
    from aipictures.intent_quality import repair_anatomy
    data=plan();data['timeline']=[dict(start=0,end=.5,description='少女前肢伸出，爪子朝镜头')]
    class Session:
        def complete(self,*args,**kwargs):
            return json.dumps(dict(positive_prompt='少女抬起右手',descriptions=['右臂伸展，手掌朝向镜头'])),{}
    fixed=json.loads(repair_anatomy(Session(),json.dumps(data),{'appearance':{'identity':'少女'}},'模仿参考动作',tmp_path))
    assert fixed['timeline'][0]['description']=='右臂伸展，手掌朝向镜头'


def test_selected_frame_inspection_does_not_invent_an_animation_plan(tmp_path):
    from aipictures.local_intent import analyze_frame
    from aipictures.frame_motion_input import import_frames
    images=[]
    for i in (0,1):
        image=tmp_path/f'{i}.png';Image.new('RGBA',(24,32),(i*80,10,30,255)).save(image);images.append(image)
    owned=tmp_path/'owned';owned.mkdir();source,_=import_frames(images,12,owned,threading.Event())
    class Session:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def complete(self,messages,**kwargs):
            assert len(messages[1]['content'])==1
            return json.dumps(dict(description='当前帧主体抬起手臂。')),{}
    result=analyze_frame({'name':'protocol fixture'},source,1,tmp_path/'analysis',threading.Event(),lambda *_:None,session_factory=Session)
    assert result['frame_analysis']['index']==1 and result['frame_analysis']['time']==pytest.approx(1/12)
    assert result['engine_released'] and 'plan' not in result and result['frame_sha256']
