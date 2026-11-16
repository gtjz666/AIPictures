"""Godot connection and explicit, draggable component exports."""
import json,re
from pathlib import Path
from PySide6.QtCore import Qt,QMimeData,QUrl,QPoint
from PySide6.QtGui import QDrag,QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,
    QFileDialog,QComboBox,QSpinBox,QTableWidget,QTableWidgetItem,QApplication,QInputDialog)
from .godot_assets import project_root,install_addon,export_asset,ACTIONS
from .storage import write_json


class DragSceneButton(QPushButton):
    def __init__(self):
        super().__init__('拖入Godot场景');self.scene=None;self.origin=QPoint();self.setEnabled(False)

    def mousePressEvent(self,event):
        self.origin=event.position().toPoint();super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.scene and event.buttons()&Qt.MouseButton.LeftButton and (event.position().toPoint()-self.origin).manhattanLength()>=QApplication.startDragDistance():
            mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(self.scene))]);drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.DropAction.CopyAction)
        else:super().mouseMoveEvent(event)


class GodotExportDialog(QDialog):
    def __init__(self,controller,*,frames=None,image=None,audio=None,fps=8,parent=None):
        super().__init__(parent or controller.window);self.controller=controller;self.frames=list(frames or []);self.image=image;self.audio=audio;self.result=None;self.closed=False;self.busy=False;self.extra_animations={}
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);self.setWindowTitle('Godot组件导出');self.resize(580,570)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        row=QHBoxLayout();self.project=QLineEdit(str(controller.project or ''));row.addWidget(self.project,1)
        browse=QPushButton('选择…');browse.clicked.connect(self.choose_project);row.addWidget(browse);form.addRow('Godot项目',row)
        self.asset_name=QLineEdit('character' if frames else 'sound' if audio else 'image');form.addRow('组件名称',self.asset_name)
        self.preset=QComboBox()
        options=[('动画素材','animated'),('双向移动角色（左右镜像）','two_way'),('四向移动角色（分别指定帧）','four_way'),('平台角色（行走／奔跑／跳跃／攻击）','platformer')] if frames else [('音效播放节点','audio')] if audio else [('图片节点','image')]
        for label,key in options:self.preset.addItem(label,key)
        form.addRow('用途预设',self.preset)
        self.action_name=QComboBox()
        for label,key in [('默认','default'),*ACTIONS]:self.action_name.addItem(label,key)
        if frames:form.addRow('当前素材动作（动画素材用）',self.action_name)
        self.extra_button=QPushButton('关联其他动作帧文件夹…');self.extra_button.clicked.connect(self.add_action)
        self.extra_note=QLabel();self.extra_note.setWordWrap(True)
        self.extra_clear=QPushButton('清除关联动作');self.extra_clear.clicked.connect(lambda:(self.extra_animations.clear(),self.extra_note.clear()))
        if frames:layout.addWidget(self.extra_button);layout.addWidget(self.extra_note);layout.addWidget(self.extra_clear)
        self.rate=QSpinBox();self.rate.setRange(1,60);self.rate.setValue(fps)
        self.pixel_height=QSpinBox();self.pixel_height.setRange(0,2048);self.pixel_height.setSpecialValueText('保留原尺寸')
        if frames:form.addRow('动画FPS',self.rate)
        if frames or image:form.addRow('像素高度（最近邻缩放）',self.pixel_height)
        self.ranges=QTableWidget(4,3);self.ranges.setHorizontalHeaderLabels(['方向','起始帧','结束帧']);self.ranges.verticalHeader().hide();self.ranges.setMaximumHeight(165)
        for row,(label,key) in enumerate([('下','walk_down'),('上','walk_up'),('左','walk_left'),('右','walk_right')]):
            item=QTableWidgetItem(label);item.setFlags(Qt.ItemFlag.ItemIsEnabled);item.setData(Qt.ItemDataRole.UserRole,key);self.ranges.setItem(row,0,item)
            for col in (1,2):
                spin=QSpinBox();spin.setRange(0,len(self.frames));spin.setSpecialValueText('请选择');self.ranges.setCellWidget(row,col,spin)
        self.range_note=QLabel(f'当前共{len(self.frames)}帧。四向需分别指定帧范围（从1开始），或关联各方向行走帧文件夹；不会自动补造方向。');self.range_note.setWordWrap(True)
        layout.addWidget(self.range_note);layout.addWidget(self.ranges)
        self.sound_path=QLineEdit();self.sound_path.setPlaceholderText('可选：关联已生成的脚步声WAV／OGG／MP3')
        row=QHBoxLayout();row.addWidget(self.sound_path,1);self.sound_button=QPushButton('关联脚步声…');self.sound_button.clicked.connect(self.choose_audio);row.addWidget(self.sound_button);layout.addLayout(row)
        self.status=QLabel('导出到项目后拖入场景。角色默认WASD移动、Shift奔跑、Space跳跃、J攻击；可在Godot内修改键位。');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.export=QPushButton('导出组件到项目');self.export.clicked.connect(self.save);layout.addWidget(self.export)
        row=QHBoxLayout();self.drag=DragSceneButton();row.addWidget(self.drag,1);self.reveal=QPushButton('打开位置');self.reveal.setEnabled(False);self.reveal.clicked.connect(self.reveal_result);row.addWidget(self.reveal);layout.addLayout(row)
        self.preset.currentIndexChanged.connect(self.update_preset);self.update_preset()

    def choose_project(self):
        path=QFileDialog.getExistingDirectory(self,'选择包含project.godot的文件夹',self.project.text())
        if path:self.project.setText(path)

    def choose_audio(self):
        path,_=QFileDialog.getOpenFileName(self,'关联脚步声','','Audio (*.wav *.ogg *.mp3)')
        if path:self.sound_path.setText(path)

    def reveal_result(self):
        if self.result:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.result['scene']).parent)))

    def update_preset(self):
        key=self.preset.currentData();self.ranges.setVisible(key=='four_way');self.range_note.setVisible(key=='four_way')
        self.action_name.setEnabled(key=='animated')
        self.sound_path.setVisible(key in ('two_way','four_way','platformer'));self.sound_button.setVisible(key in ('two_way','four_way','platformer'))

    def add_action(self):
        names=[];codes=[]
        for label,action in ACTIONS:
            for direction,suffix in ([('下','down'),('上','up'),('左','left'),('右','right')] if self.preset.currentData()=='four_way' else [('左右镜像','right')]):
                names.append(label+' · '+direction);codes.append(action+'_'+suffix)
        label,ok=QInputDialog.getItem(self,'关联动作','动作与方向',names,editable=False)
        if not ok:return
        path=QFileDialog.getExistingDirectory(self,'选择按文件名顺序排列的PNG动作帧文件夹')
        if not path:return
        frames=sorted(Path(path).glob('*.png'),key=lambda p:[int(v) if v.isdigit() else v.lower() for v in re.split(r'(\d+)',p.name)])
        if not frames:self.status.setText('文件夹中没有PNG动画帧。');return
        self.extra_animations[codes[names.index(label)]]=frames
        self.extra_note.setText('已关联：'+', '.join(self.extra_animations))

    def options(self):
        key=self.preset.currentData();animations={}
        if key in ('animated','two_way','platformer'):animations[self.action_name.currentData() if key=='animated' else 'walk_right']=self.frames
        if key=='four_way':
            for row in range(4):
                name=self.ranges.item(row,0).data(Qt.ItemDataRole.UserRole)
                start,end=(self.ranges.cellWidget(row,col).value() for col in (1,2))
                if start==end==0 and name in self.extra_animations:continue
                if not 1<=start<=end<=len(self.frames):raise ValueError('请指定每个方向的有效起止帧。')
                animations[name]=self.frames[start-1:end]
        for name,frames in self.extra_animations.items():
            if name in animations:raise ValueError('附加动作与基础动作同名，请清除附加动作或更换预设。')
            animations[name]=frames
        audio=self.sound_path.text().strip() if key in ('two_way','four_way','platformer') else self.audio
        return dict(project=self.project.text(),name=self.asset_name.text(),preset=key,animations=animations,image=self.image,audio=audio or None,fps=self.rate.value(),output_height=self.pixel_height.value())

    def save(self):
        w=self.controller.window
        if w.current or w.preparing:self.status.setText('请等当前任务完成后导出。');return
        try:
            options=self.options();project_root(options['project'])
        except (ValueError,OSError) as exc:self.status.setText(str(exc));return
        self.busy=True;self.export.setEnabled(False);self.drag.setEnabled(False);self.reveal.setEnabled(False)
        w.preparing=True;w.prepare_cancel.clear();w.task_display.start();w.progress.setRange(0,0);self.status.setText('正在导出Godot组件…')
        def done(kind,data):
            if kind not in ('result','error','cancelled'):return
            self.busy=False;w.preparing=False;w.task_display.finish('completed' if kind=='result' else 'failed' if kind=='error' else 'cancelled');w.generation_type_changed()
            if kind=='result':
                self.result=data;self.controller.connect_project(options['project']);w.status.setText('Godot组件已导出。')
            else:w.status.setText(str(data))
            if self.closed:return
            self.export.setEnabled(True)
            if kind=='result':
                self.drag.scene=Path(data['scene']);self.drag.setEnabled(True);self.reveal.setEnabled(True)
                self.status.setText('已导出。可从这里拖入Godot场景，也可在插件中拖入组件。')
            else:self.status.setText(str(data))
        w.launch(lambda emit:export_asset(**options,cancel=w.prepare_cancel),done)

    def closeEvent(self,event):
        self.closed=True
        if self.busy:self.controller.window.prepare_cancel.set()
        super().closeEvent(event)


class GodotController:
    def __init__(self,window):
        self.window=window;self.project=None;self.dialog=None
        try:self.project=project_root(json.loads((window.api_controller.data/'godot-project.json').read_text('utf-8'))['project'])
        except (OSError,ValueError,KeyError):pass
        menu=window.menuBar().addMenu('Godot');menu.addAction('连接项目／安装插件…',self.install)
        menu.addAction('导出当前图片组件…',self.image);menu.addAction('导出当前动画组件…',self.animation);menu.addAction('导出当前音频组件…',self.audio)

    def connect_project(self,path):
        self.project=project_root(path);write_json(self.window.api_controller.data/'godot-project.json',dict(project=str(self.project)))

    def install(self):
        path=QFileDialog.getExistingDirectory(self.window,'选择Godot项目',str(self.project or ''))
        if not path:return
        try:
            install_addon(path,Path(__file__).resolve().parents[1]);self.connect_project(path)
            self.window.status.setText('插件已安装。请在Godot项目设置→插件中启用AlI游戏素材，从右侧AlI素材面板打开生成窗口。')
        except (OSError,ValueError) as exc:self.window.status.setText(str(exc))

    def show(self,**kwargs):
        self.dialog=GodotExportDialog(self,**kwargs);self.dialog.show();self.dialog.raise_();return self.dialog

    def image(self):
        if not self.window.output:self.window.status.setText('请先生成或打开成品图片。');return
        return self.show(image=self.window.output)

    def audio(self):
        audio=self.window.audio_controller.audio
        if not audio:self.window.status.setText('请先生成或打开音频。');return
        return self.show(audio=audio)

    def animation(self):
        from .frame_selection import open_selection
        manifest=self.window.video_controller.player.manifest
        if not manifest:self.window.status.setText('请先生成或打开完整动画。');return
        open_selection(self.window,manifest)

    def frames(self,paths,fps,parent=None):return self.show(frames=paths,fps=fps,parent=parent)

    def launch_context(self,project,kind):
        if project:self.connect_project(project);self.window.setWindowTitle('AlI · '+self.project.name)
        b=self.window.workbench
        if kind in ('sfx','music'):
            b.select_category('audio');c=self.window.audio_controller.kind;c.setCurrentIndex(c.findData(kind))
        elif kind=='animation':b.select_category('sprite');b.sprite_mode.setCurrentIndex(b.sprite_mode.findData('walk'))
        else:b.select_category('sprite');b.sprite_mode.setCurrentIndex(0)
        b.right_tabs.setCurrentIndex(1)
