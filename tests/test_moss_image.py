import copy,json,threading
from pathlib import Path
import pytest
from aipictures import moss_image as moss


def params(mode='layout'):
 return dict(moss_mode=mode,width=1024,height=1024,seed=42,steps=30 if mode=='edit' else 25,cfg=4. if mode=='edit' else 2.5,positive='将图四的主体改成图二的画风，保留主体动作。' if mode=='edit' else '中文主菜单',negative='',layout=moss.draft(),references={2:{},4:{}} if mode=='edit' else {})


def test_official_coordinate_contract_and_literal_user_text():
 d=moss.draft();d.update(width=1536,height=1024);d['items']=[dict(label='text',text='保留\n中英文 MIX',caption='不要改写',bbox=[176,224,800,864])]
 out=json.loads(moss.compile_layout(d));assert out['items'][0]['bbox']==[-288,-592,352,32]
 assert out['items'][0]['text']=='保留\n中英文 MIX' and out['items'][0]['caption']=='不要改写'
 assert 'width' not in out and out['bbox_format']=='yxyx'
 d['items'][0]['bbox']=[176.2,224.3,800.1,864.2]
 assert json.loads(moss.compile_layout(d))['items'][0]['bbox']==[-288,-592,353,33]
 d['items'][0]['bbox']=[0,0,1600,1024]
 with pytest.raises(ValueError):moss.compile_layout(d)


def test_native_layout_and_edit_have_separate_conditions_no_assistant():
 p=params();full=moss.graph({},p);positive=full['positive']['inputs']['text']
 assert json.loads(positive)['items'][0]['text']=='星界远征'
 assert full['clip']['inputs']['type']=='moss_image'
 assert full['sample']['inputs']['steps']==25 and full['sample']['inputs']['cfg']==2.5
 assert not any(n['class_type'] in ['TextGenerate','ModelSamplingSD3','TextEncodeMOSSImageEdit','LoraLoaderModelOnly'] for n in full.values())
 p=params('edit');g=moss.graph({},p,names=['reference_1.png','reference_2.png'])
 assert g['positive']['inputs']['prompt']=='将Image 2的主体改成Image 1的画风，保留主体动作。'
 assert g['positive']['inputs']['images.image_0']==['scale1',0]
 assert g['negative']['inputs']['images.image_1']==['scale2',0]
 assert g['edit_lora']['inputs']['strength_model']==1.0 and g['sample']['inputs']['scheduler']=='normal'
 assert 'clip' not in moss.graph({},p,stage='sample') and 'model' not in moss.graph({},p,stage='encode',names=['r.png','s.png'])
 assert moss.graph({},p,stage='decode')['decode']['inputs']['samples']==['condition',2]


@pytest.mark.parametrize('width,height,mode,refs',[(1023,1024,'layout',{}),(4096,4096,'layout',{}),(1024,1024,'layout',{1:{}}),(1024,1024,'edit',{}),(1024,1024,'edit',{5:{}})])
def test_invalid_requests_fail_before_start(width,height,mode,refs):
 with pytest.raises(ValueError):moss.validate(width,height,42,25,2.5,mode,refs)


def test_runtime_refuses_changed_dimensions_and_unverified_before_engine(tmp_path):
 from aipictures.moss_runtime import generate
 p=params();p['moss_settings']={'validated':False};p['layout']['width']=1536
 with pytest.raises(ValueError,match='尚未'):generate(tmp_path,p,threading.Event(),lambda *_:None)
 with pytest.raises(ValueError,match='不一致'):generate(tmp_path,p,threading.Event(),lambda *_:None,research=True)
 assert not (tmp_path/'moss-started.json').exists()


def test_workspace_drag_resize_snapshot_and_import_guard(tmp_path,monkeypatch):
 from PySide6.QtWidgets import QWidget,QApplication
 from aipictures.moss_workspace import MossWindow,Region
 class Host(QWidget):
  connected=False;current=None;preparing=False;pending=[]
 app=QApplication.instance() or QApplication([])
 host=Host();w=MossWindow(host)
 region=next(i for i in w.scene.items() if isinstance(i,Region) and i.index==0)
 region.setPos(160,140)
 assert w.layout_data['items'][0]['bbox'][:2]==[160,140]
 w.width.setValue(1536)
 assert w.layout_data['items'][0]['bbox'][0]==240 and w.layout_data['items'][0]['bbox'][1]==140
 frozen,_=w.snapshot();w.prompt.setPlainText('新的手写要求')
 assert frozen['positive']!=w.prompt.toPlainText() and frozen['layout']['summary']['caption']==frozen['positive']
 w.mode.setCurrentIndex(1);w.references={2:tmp_path/'b.png',4:tmp_path/'d.png'};w.prompt.setPlainText('保留图四主体，采用图二画风。')
 with pytest.raises(ValueError,match='110'):w.snapshot()
 w.width.setValue(1024)
 p,refs=w.snapshot();assert list(refs)==[2,4] and p['steps']==30 and not w.regions.isEnabled()
 assert p['positive']=='保留图四主体，采用图二画风。'
