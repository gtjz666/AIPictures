"""Independent manual MOSS workspace; no automatic analysis of user references."""
import copy,json,secrets,shutil,threading
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QRectF
from PySide6.QtGui import QColor,QPen,QPixmap,QBrush
from PySide6.QtWidgets import (QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QFormLayout,QSplitter,
 QComboBox,QPlainTextEdit,QSpinBox,QDoubleSpinBox,QPushButton,QLabel,QFileDialog,
 QMessageBox,QGraphicsView,QGraphicsScene,QGraphicsRectItem,QGraphicsSimpleTextItem,QListWidget,
 QLineEdit,QAbstractItemView)
from . import moss_image as moss
from .storage import DATA,new_job,write_json
from .task_display import TaskProgress
from .workflow_library import digest


class CanvasView(QGraphicsView):
 def resizeEvent(self,event):
  super().resizeEvent(event);QTimer.singleShot(0,self.fit_canvas)
 def fit_canvas(self):
  if self.scene():self.fitInView(self.scene().sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)


class Region(QGraphicsRectItem):
 def __init__(self,workspace,index,row):
  x0,y0,x1,y1=row['bbox'];super().__init__(0,0,x1-x0,y1-y0);self.workspace=workspace;self.index=index
  color=QColor('#5b83cf' if row['label']=='text' else '#ad6bcd' if row['label']=='character' else '#3caa83')
  self.setPen(QPen(color,3));self.setBrush(QBrush(QColor(color.red(),color.green(),color.blue(),35)))
  self.setFlags(self.GraphicsItemFlag.ItemIsMovable|self.GraphicsItemFlag.ItemIsSelectable|self.GraphicsItemFlag.ItemSendsGeometryChanges)
  self.setPos(x0,y0);self.label=QGraphicsSimpleTextItem(self);self.label.setBrush(QBrush(QColor('#17314e')));self.label.setPos(6,6)
  self.label.setText(f'{index+1} · '+(row.get('text') or row['caption'] or row['label'])[:30])
 def itemChange(self,change,value):
  if change==self.GraphicsItemChange.ItemPositionChange and self.scene():
   return type(value)(max(0,min(value.x(),self.workspace.layout_data['width']-self.rect().width())),max(0,min(value.y(),self.workspace.layout_data['height']-self.rect().height())))
  if change==self.GraphicsItemChange.ItemPositionHasChanged and self.scene() and not self.workspace.updating:
   row=self.workspace.layout_data['items'][self.index];x,y=self.pos().x(),self.pos().y();row['bbox']=[x,y,x+self.rect().width(),y+self.rect().height()]
   self.workspace.show_region(self.index)
  return super().itemChange(change,value)


class MossWindow(QMainWindow):
 def __init__(self,window):
  super().__init__(window);self.host=window;self.busy=False;self.cancel=threading.Event();self.owner=None;self.folder=None;self.result_path=None;self.references={};self.layout_data=moss.draft();self.updating=False
  self.setAcceptDrops(True);self.setWindowTitle('画面设计 · 排版生成与参考图编辑');self.resize(1380,900)
  root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root)
  top=QHBoxLayout();outer.addLayout(top);self.mode=QComboBox();self.mode.addItem('排版生成','layout');self.mode.addItem('参考图编辑 · 社区实验','edit');top.addWidget(self.mode)
  self.width=QSpinBox();self.height=QSpinBox()
  for box in [self.width,self.height]:box.setRange(256,4096);box.setSingleStep(16);box.setValue(1024)
  top.addWidget(QLabel('宽'));top.addWidget(self.width);top.addWidget(QLabel('高'));top.addWidget(self.height)
  self.add_button=QPushButton('添加区域');top.addWidget(self.add_button);self.add_button.clicked.connect(self.add_region)
  for title,fn in [('删除区域',self.remove_region),('打开布局…',self.open_layout),('保存布局…',self.save_layout),('导出工作流…',self.export_workflow)]:
   button=QPushButton(title);top.addWidget(button);button.clicked.connect(fn)
  split=QSplitter();outer.addWidget(split,1)
  left=QWidget();left_layout=QVBoxLayout(left);self.scene=QGraphicsScene(self);self.view=CanvasView(self.scene);self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.view.setMinimumWidth(450);left_layout.addWidget(self.view,1)
  self.preview=QLabel('生成结果在这里显示');self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setMinimumHeight(240);left_layout.addWidget(self.preview,1);split.addWidget(left)
  right=QWidget();form=QVBoxLayout(right);split.addWidget(right);split.setSizes([850,450]);self.hint=QLabel('拖动区域可改位置；右侧数值调整大小。位置是生成引导，不是像素级硬边界。');self.hint.setWordWrap(True);form.addWidget(self.hint)
  form.addWidget(QLabel('手写提示词'));self.prompt=QPlainTextEdit(self.layout_data['summary']['caption']);self.prompt.setMaximumHeight(135);form.addWidget(self.prompt)
  self.ref_list=QListWidget();self.ref_list.setMaximumHeight(110);form.addWidget(self.ref_list);ref_buttons=QHBoxLayout();form.addLayout(ref_buttons)
  self.add_ref=QPushButton('添加参考图（最多4张）');self.remove_ref=QPushButton('移除所选参考图');ref_buttons.addWidget(self.add_ref);ref_buttons.addWidget(self.remove_ref);self.add_ref.clicked.connect(self.pick_reference);self.remove_ref.clicked.connect(self.remove_reference)
  self.ref_aspect=QPushButton('采用所选图片比例');ref_buttons.addWidget(self.ref_aspect);self.ref_aspect.clicked.connect(self.reference_aspect)
  self.regions=QListWidget();self.regions.setMaximumHeight(120);form.addWidget(self.regions);self.regions.currentRowChanged.connect(self.show_region)
  self.kind=QComboBox()
  for title,value in [('文字','text'),('物体','object'),('人物区域','character')]:self.kind.addItem(title,value)
  fields=QFormLayout();form.addLayout(fields);fields.addRow('区域类型',self.kind);self.coordinates=[]
  for label in ['X','Y','宽','高']:
   box=QDoubleSpinBox();box.setRange(0,4096);box.setDecimals(1);fields.addRow(label,box);self.coordinates.append(box);box.valueChanged.connect(self.edit_region)
  self.text=QLineEdit();fields.addRow('显示文字',self.text);self.caption=QPlainTextEdit();self.caption.setMaximumHeight(80);fields.addRow('区域描述',self.caption)
  self.kind.currentIndexChanged.connect(self.edit_region);self.text.textChanged.connect(self.edit_region);self.caption.textChanged.connect(self.edit_region)
  self.steps=QSpinBox();self.steps.setRange(1,100);self.steps.setValue(25);self.cfg=QDoubleSpinBox();self.cfg.setRange(1,10);self.cfg.setValue(2.5);self.seed=QLineEdit('-1')
  controls=QHBoxLayout();form.addLayout(controls)
  for label,widget in [('步数',self.steps),('引导',self.cfg),('种子',self.seed)]:controls.addWidget(QLabel(label));controls.addWidget(widget)
  self.progress=TaskProgress();outer.addWidget(self.progress);self.status=QLabel('可编辑布局、保存草稿或导出工作流。');self.status.setWordWrap(True);outer.addWidget(self.status)
  actions=QHBoxLayout();outer.addLayout(actions)
  for title,fn in [('生成图片',self.generate),('取消',lambda:self.cancel.set()),('另存结果…',self.save_result),('用于软件预览／导出',self.use_result)]:
   button=QPushButton(title);actions.addWidget(button);button.clicked.connect(fn)
   if title=='生成图片':self.generate_button=button
  self._previous_mode='layout';self._prompts={'layout':self.prompt.toPlainText(),'edit':''}
  self.mode.currentIndexChanged.connect(self.mode_changed);self.width.valueChanged.connect(self.resize_canvas);self.height.valueChanged.connect(self.resize_canvas)
  self.scene.selectionChanged.connect(self.select_canvas_region);self.render();self.mode_changed()

 def mode_changed(self):
  mode=self.mode.currentData();self._prompts[self._previous_mode]=self.prompt.toPlainText();self.prompt.setPlainText(self._prompts[mode]);self._previous_mode=mode
  editing=mode=='edit'
  for widget in [self.add_ref,self.remove_ref,self.ref_aspect,self.ref_list]:widget.setVisible(editing)
  for widget in [self.regions,self.kind,self.text,self.caption,*self.coordinates,self.add_button]:widget.setEnabled(not editing)
  self.steps.setValue(30 if editing else 25);self.cfg.setValue(4 if editing else 2.5)
  self.hint.setText('填写每张参考图的用途，如“保留图2人物外形，采用图1动作与表情”。社区扩展，换姿势效果需要逐例检查。参考图合计约100万像素，自动等比缩放。' if editing else '拖动区域改变位置；右侧数值调整大小。边界框是生成引导，不保证精确裁切或原图身份。')
  self.render()

 def render(self):
  self.updating=True;index=self.regions.currentRow();self.scene.clear();self.regions.clear();w,h=self.layout_data['width'],self.layout_data['height'];self.scene.setSceneRect(0,0,w,h);self.scene.setBackgroundBrush(QBrush(QColor('#f4f7fc')))
  if self.mode.currentData()=='edit':
   for i,(number,path) in enumerate(sorted(self.references.items())):
    pix=QPixmap(str(path)).scaled(int(w/2-24),int(h/2-48),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    item=self.scene.addPixmap(pix);item.setPos((i%2)*w/2+12,(i//2)*h/2+30)
    label=self.scene.addSimpleText('图'+str(number));label.setPos((i%2)*w/2+12,(i//2)*h/2)
   self.updating=False;self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio);return
  for i,row in enumerate(self.layout_data['items']):self.regions.addItem(f'{i+1} · '+(row.get('text') or row['caption'] or row['label'])[:35]);self.scene.addItem(Region(self,i,row))
  self.updating=False
  if self.regions.count():self.regions.setCurrentRow(max(0,min(index,self.regions.count()-1)));self.show_region(self.regions.currentRow())
  self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

 def show_region(self,index):
  if self.updating or not 0<=index<len(self.layout_data['items']):return
  self.updating=True;row=self.layout_data['items'][index];self.kind.setCurrentIndex(self.kind.findData(row['label']));self.text.setText(row.get('text',''));self.caption.setPlainText(row['caption']);x,y,x1,y1=row['bbox']
  for widget,value in zip(self.coordinates,[x,y,x1-x,y1-y]):widget.setValue(value)
  self.updating=False

 def select_canvas_region(self):
  selected=self.scene.selectedItems()
  if selected and isinstance(selected[0],Region):self.regions.setCurrentRow(selected[0].index)

 def edit_region(self,*_):
  index=self.regions.currentRow()
  if self.updating or not 0<=index<len(self.layout_data['items']):return
  x,y,w,h=[box.value() for box in self.coordinates];cw,ch=self.layout_data['width'],self.layout_data['height'];x=min(x,cw-1);y=min(y,ch-1);w=max(1,min(w,cw-x));h=max(1,min(h,ch-y))
  self.layout_data['items'][index]=dict(label=self.kind.currentData(),text=self.text.text(),caption=self.caption.toPlainText(),bbox=[x,y,x+w,y+h]);self.render()

 def add_region(self):
  if len(self.layout_data['items'])>=32:return
  self.layout_data['items'].append(dict(label='object',caption='新物体',bbox=[32,32,256,256]));self.render();self.regions.setCurrentRow(self.regions.count()-1)

 def remove_region(self):
  index=self.regions.currentRow()
  if index>=0:self.layout_data['items'].pop(index);self.render()

 def resize_canvas(self):
  if self.updating:return
  oldw,oldh=self.layout_data['width'],self.layout_data['height'];w,h=self.width.value(),self.height.value()
  for row in self.layout_data['items']:row['bbox']=[v*(w/oldw if i%2==0 else h/oldh) for i,v in enumerate(row['bbox'])]
  self.layout_data.update(width=w,height=h);self.render()

 def dragEnterEvent(self,event):
  if event.mimeData().hasUrls():event.acceptProposedAction()
 def dropEvent(self,event):
  if self.busy:return
  files=[url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
  self.mode.setCurrentIndex(1);self.load_references(files);event.acceptProposedAction()
 def load_references(self,files):
  from PIL import Image
  for filename in files:
   if len(self.references)>=4:break
   try:
    with Image.open(filename) as image:image.verify()
    number=next(n for n in range(1,5) if n not in self.references);self.references[number]=Path(filename)
   except (OSError,ValueError) as exc:self.status.setText('无法读取图片：'+str(exc))
  self.refresh_references()
 def pick_reference(self):
  files,_=QFileDialog.getOpenFileNames(self,'选择参考图片','','图片 (*.png *.jpg *.jpeg *.webp)')
  self.load_references(files)

 def reference_aspect(self):
  item=self.ref_list.currentItem()
  if item is None:self.status.setText('先选择一张作为输出比例的参考图。');return
  from PIL import Image
  with Image.open(self.references[item.data(Qt.ItemDataRole.UserRole)]) as image:w,h=image.size
  scale=(1048576/(w*h))**.5
  self.width.setValue(max(256,min(4096,round(w*scale/16)*16)));self.height.setValue(max(256,min(4096,round(h*scale/16)*16)))
  self.status.setText('已采用所选参考图的近似比例，输出约100万像素。')
 def remove_reference(self):
  item=self.ref_list.currentItem()
  if item:self.references.pop(item.data(Qt.ItemDataRole.UserRole));self.refresh_references()

 def refresh_references(self):
  self.ref_list.clear()
  for n,path in sorted(self.references.items()):self.ref_list.addItem(f'图{n} · {path.name}');self.ref_list.item(self.ref_list.count()-1).setData(Qt.ItemDataRole.UserRole,n)
  self.render()

 def snapshot(self):
  seed=int(self.seed.text());seed=secrets.randbelow(2**53) if seed==-1 else seed;mode=self.mode.currentData();self.layout_data['summary']['caption']=self.prompt.toPlainText()
  c=moss.settings(DATA);params=dict(mode='moss_image',moss_mode=mode,backend='standalone',model_family='moss_image',positive=self.prompt.toPlainText(),negative='',width=self.width.value(),height=self.height.value(),steps=self.steps.value(),cfg=self.cfg.value(),seed=seed,layout=copy.deepcopy(self.layout_data),references={},prompt_expander=False,protocol=moss.PROTOCOL,moss_settings=c,url=self.host.client.url if self.host.connected else None)
  refs=dict(sorted(self.references.items())) if mode=='edit' else {};moss.validate(params['width'],params['height'],seed,params['steps'],params['cfg'],mode,refs)
  if mode=='layout':moss.compile_layout(params['layout'])
  else:__import__('aipictures.multi_reference',fromlist=['bind_text']).bind_text(params['positive'],list(refs),label='Image')
  if not params['positive'].strip():raise ValueError('请填写手写提示词。')
  return params,refs

 def open_layout(self):
  path,_=QFileDialog.getOpenFileName(self,'打开布局草稿','','JSON (*.json)')
  if not path:return
  try:
   if Path(path).stat().st_size>1024**2:raise ValueError('草稿超过1MB。')
   draft=json.loads(Path(path).read_text('utf-8'));moss.compile_layout(draft);self.layout_data=draft;self.updating=True;self.width.setValue(draft['width']);self.height.setValue(draft['height']);self.updating=False;self.prompt.setPlainText(draft['summary']['caption']);self.render()
  except (OSError,ValueError,TypeError,KeyError) as exc:self.status.setText(str(exc))

 def save_layout(self):
  try:
   self.layout_data['summary']['caption']=self.prompt.toPlainText();moss.compile_layout(self.layout_data);path,_=QFileDialog.getSaveFileName(self,'保存布局草稿','moss-layout.json','JSON (*.json)')
   if path:write_json(path,self.layout_data)
  except ValueError as exc:self.status.setText(str(exc))

 def export_workflow(self):
  try:
   params,refs=self.snapshot();params['references']={n:{} for n in refs};graph=moss.graph(params['moss_settings'],params,names=[f'reference_{i}.png' for i in range(1,len(refs)+1)])
   path,_=QFileDialog.getSaveFileName(self,'导出ComfyUI API工作流','moss-workflow-api.json','JSON (*.json)')
   if path:write_json(path,graph);self.status.setText('已导出API工作流；参考图编辑需在ComfyUI上传对应reference_编号.png。')
  except (ValueError,TypeError) as exc:self.status.setText(str(exc))

 def generate(self):
  if self.busy:return
  if self.host.current or self.host.preparing or self.host.pending:self.status.setText('请等待软件当前生成与排队任务完成。');return
  try:
   params,refs=self.snapshot()
   if not params['moss_settings']:raise ValueError('MOSS尚未安装并完成本机验证，可先保存布局或导出工作流。')
   if params['moss_mode'] not in params['moss_settings'].get('validated_modes',[]):raise ValueError('此MOSS模式尚未完成本机流程验证。')
   params['references']={n:None for n in refs}
   folder=new_job(moss.graph(params['moss_settings'],params,stage='full',names=[f'reference_{i}.png' for i in range(1,len(refs)+1)]),params)
   for n,path in refs.items():
    sha=digest(path);target=folder/'references'/f'{n}{path.suffix.lower()}';target.parent.mkdir(exist_ok=True);shutil.copyfile(path,target)
    if digest(target)!=sha:raise ValueError('参考图在复制时变化。')
    params['references'][n]=dict(path=str(target),sha256=sha)
   self.busy=True;self.folder=folder;self.cancel=threading.Event();self.generate_button.setEnabled(False);self.progress.begin();self.progress.setRange(0,0);self.status.setText('正在核验本次模型与输入…')
   def run(emit):
    from .moss_runtime import generate
    def save(status,error=None):write_json(folder/'job.json',dict(schema_version=1,kind='image',status=status,params=params,error=error),durable=True)
    save('running')
    try:result=generate(folder,params,self.cancel,emit);save('completed');return result
    except Exception as exc:save('cancelled' if self.cancel.is_set() else 'failed',str(exc));raise
   self.host.launch(run,self.on_worker_event)
  except (ValueError,OSError,TypeError) as exc:self.status.setText(str(exc))

 def on_worker_event(self,kind,data):
  if kind=='moss_process':self.owner=data['owner']
  elif kind=='moss_stage':self.status.setText(data['message']);self.progress.setRange(0,0)
  elif kind=='progress':self.progress.setRange(0,100);self.progress.setValue(round(100*data['value']/max(1,data['max'])))
  elif kind in ['result','error','cancelled']:
   self.busy=False;self.owner=None;self.generate_button.setEnabled(True);self.progress.end(100 if kind=='result' else 0)
   if kind=='result':self.result_path=Path(data['images'][0]);self.show_result();self.status.setText('MOSS生成完成。请核对文字、布局或参考编辑效果。')
   else:self.status.setText('已取消。' if self.cancel.is_set() else str(data))
   self.host.load_gallery();QTimer.singleShot(0,self.host.start_next)

 def show_result(self):
  if self.result_path:self.preview.setPixmap(QPixmap(str(self.result_path)).scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
 def save_result(self):
  if not self.result_path:return
  path,_=QFileDialog.getSaveFileName(self,'另存图片','moss-result.png','PNG (*.png)')
  if path:shutil.copyfile(self.result_path,path)
 def use_result(self):
  if self.result_path:self.host.show_image(str(self.result_path));self.host.workbench.select_category('sprite')
 def shutdown(self):
  self.cancel.set()
  if self.owner:self.owner.close()
 def closeEvent(self,event):
  if self.busy:self.shutdown()
  event.accept()
 def resizeEvent(self,event):
  super().resizeEvent(event)
  if hasattr(self,'view'):self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio);self.show_result()


def open_workspace(window):
 if not hasattr(window,'moss_window'):window.moss_window=MossWindow(window)
 window.moss_window.show();window.moss_window.raise_();return window.moss_window
