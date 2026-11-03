"""Dockable creation workspace: canvas left, prompts and animation right."""
import json
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QByteArray
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QToolButton,
    QButtonGroup,QDialog,QTabWidget,QScrollArea,QTableWidget,QTableWidgetItem,QHeaderView,
    QSizePolicy,QMainWindow,QDockWidget,QToolBar,QBoxLayout,QSlider,QCheckBox)
from .storage import write_json
from .transparent_preview import TransparentPreview


class WorkspaceDock(QDockWidget):
    def __init__(self,title,name,content,parent):
        super().__init__(title,parent);self.setObjectName(name);self.setWidget(content)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        maximize=QAction('最大化面板',self);maximize.triggered.connect(self.maximize_panel)
        dock=QAction('停靠面板',self);dock.triggered.connect(lambda:self.setFloating(False))
        self.addActions([maximize,dock,self.toggleViewAction()])

    def maximize_panel(self):
        self.setFloating(True);self.showMaximized()


class ReferencePlayback(QWidget):
    """Imported motion preview; never marked as generated output."""
    def __init__(self,window):
        super().__init__();self.window=window;self.paths=[];self.index=0;self.fps=24.
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0)
        self.play=QPushButton('播放');self.play.clicked.connect(self.toggle);row.addWidget(self.play)
        self.slider=QSlider(Qt.Orientation.Horizontal);row.addWidget(self.slider,1)
        self.slider.valueChanged.connect(self.seek);self.label=QLabel();row.addWidget(self.label)
        self.loop=QCheckBox('循环');self.loop.setChecked(True);row.addWidget(self.loop)
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.hide()

    def load(self,paths):
        self.timer.stop();self.paths=[Path(p) for p in paths];self.index=0
        self.slider.setRange(0,max(0,len(self.paths)-1));self.seek(0);self.play.setText('播放');self.show()

    def seek(self,index):
        if not self.paths:return
        self.index=index;w=self.window;w.pixmap=QPixmap(str(self.paths[index]))
        w.output=None;w.preview_path=str(self.paths[index]);w.preview_role='motion_reference'
        w.preview.set_clickable(False);w.fit_preview();self.label.setText(f'{index+1}/{len(self.paths)}')

    def toggle(self):
        if self.timer.isActive():self.timer.stop();self.play.setText('播放')
        elif self.paths:
            if self.index==len(self.paths)-1:self.slider.setValue(0)
            self.timer.start(round(1000/self.fps));self.play.setText('暂停')

    def advance(self):
        if self.index==len(self.paths)-1 and not self.loop.isChecked():
            self.timer.stop();self.play.setText('播放');return
        self.slider.setValue((self.index+1)%len(self.paths))

    def stop(self):
        self.timer.stop();self.hide()


class Workbench:
    def __init__(self,w):
        self.window=w;self.data=w.api_controller.data;self.plan=None;self._restored=False
        self.hidden=QWidget(w);self.hidden.hide()
        self.prompts=w.positive.parentWidget().parentWidget()
        self.prompts.layout().setDirection(QBoxLayout.Direction.TopToBottom)
        self.legacy_root=w.takeCentralWidget();self.legacy_root.hide()
        self.legacy_root.setParent(self.hidden)
        w.removeDockWidget(w.diagnostics);w.diagnostics.setParent(self.hidden);w.output_shortcut.setEnabled(False)
        w.tabs.setParent(w);w.setCentralWidget(w.tabs)
        old_page=w.tabs.widget(0);w.tabs.removeTab(0);old_page.setParent(self.hidden)
        self.workspace=QMainWindow();self.workspace.setDockNestingEnabled(True)
        self.workspace.setDockOptions(QMainWindow.DockOption.AllowNestedDocks |
            QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AnimatedDocks)
        w.tabs.insertTab(0,self.workspace,'创作');w.tabs.setCurrentIndex(0);self.docks={}
        for control in (w.creation_summary,w.reference_label,w.context_label,w.intent_hint,w.style_status,w.seed_notice,w.caption):
            control.setParent(self.hidden)
        w.preview.setText('拖入参考素材');w.preview.setMinimumSize(320,240)
        w.preview.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        w.sequence_preview.sheet.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        w.sequence_preview.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        canvas=QWidget();cv=QVBoxLayout(canvas);cv.setContentsMargins(6,6,6,6);cv.addWidget(w.sequence_preview,1)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(w.image_save);actions.addWidget(w.image_reuse);cv.addLayout(actions)
        self.reference_player=ReferencePlayback(w);cv.addWidget(self.reference_player)
        cv.addWidget(w.animation_player);cv.addWidget(w.video_controller.player)
        self.canvas=self.dock('画布','canvas',canvas)
        w.image_save.setEnabled(False);w.image_reuse.setEnabled(False)
        self.make_settings(w);self.make_prompts(w);self.make_animation(w)
        w.task_display.setMinimumWidth(240);self.task=self.dock('当前任务','task',w.task_display)
        self.make_toolbar(w);self.reset_layout(save=False)
        w.generation_type.hide();w.animation_action.setCurrentIndex(w.animation_action.findData('custom'))
        w.positive.setMinimumHeight(80);w.negative.setMinimumHeight(64)
        w.positive.setMaximumHeight(16777215);w.negative.setMaximumHeight(16777215)
        w.intent_controller.panel.setParent(self.hidden);w.intent_controller.input.hide()
        w.video_controller.motion.changed.connect(self.motion_changed)
        self.refresh_reference();QTimer.singleShot(0,self.restore_layout)

    def dock(self,title,name,content):
        if name in ('prompts','animation'):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);content=scroll
        result=WorkspaceDock(title,'workspace_'+name,content,self.workspace);self.docks[name]=result;return result

    def make_settings(self,w):
        content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(6,6,6,6)
        self.tabs=QTabWidget();layout.addWidget(self.tabs);self.sections={}
        self.tabs.tabBar().hide()
        for key,title in [('creation','生成'),('image','画面'),('sampling','采样'),('connection','连接')]:
            scroll=w.settings_dialogs[key].findChild(QScrollArea)
            if scroll:
                page=scroll.takeWidget();container=QScrollArea();container.setWidgetResizable(True);container.setWidget(page)
                self.sections[key]=self.tabs.addTab(container,title)
        self.settings=self.dock('创作设置','settings',content)
        for button in w.settings_buttons.values():button.setParent(self.hidden)
        w.api_controller.button.setParent(self.hidden);w.api_controller.summary.setParent(self.hidden)

    def make_prompts(self,w):
        c=w.intent_controller;content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(8,6,8,6)
        self.reference_thumb=TransparentPreview();self.reference_thumb.setFixedSize(44,44)
        self.reference_thumb.activated.connect(lambda:w.show_image(str(w.reference_path),role='reference') if w.reference_path else None)
        self.reference_name=QLabel();self.reference_name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        reference=QHBoxLayout();reference.addWidget(self.reference_thumb);reference.addWidget(self.reference_name,1)
        reference.addWidget(w.attach_reference_button)
        w.attach_reference_button.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Preferred)
        remove=QPushButton('移除');remove.clicked.connect(w.clear_reference);reference.addWidget(remove)
        self.remove_reference=remove;layout.addLayout(reference)
        remove.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Preferred)
        c.role.setItemText(0,'角色 / 外观');c.role.setItemText(1,'画风 / 布局');c.role.setItemText(2,'编辑底图')
        layout.addWidget(c.role);layout.addWidget(self.prompts,1)
        c.organize.setText('自动生成提示词');layout.addWidget(c.organize);layout.addWidget(c.note)
        self.prompt_dock=self.dock('提示词','prompts',content)
        self.details=QToolButton();self.details.setText('提示词');self.details.setCheckable(True)
        self.details.toggled.connect(self.prompt_dock.setVisible);self.prompt_dock.visibilityChanged.connect(self.details.setChecked)

    def make_animation(self,w):
        content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(8,6,8,6)
        action=QHBoxLayout();action.addWidget(w.animation_action_label);action.addWidget(w.animation_action,1);layout.addLayout(action)
        layout.addWidget(w.video_controller.motion)
        taken=w.walk_form.takeRow(w.video_controller.seconds)
        if taken.labelItem:taken.labelItem.widget().hide()
        duration=QHBoxLayout();duration.addWidget(QLabel('时长 / 秒'));duration.addWidget(w.video_controller.seconds,1);layout.addLayout(duration)
        controls=QHBoxLayout();self.analyze_motion=QPushButton('分析动作');self.analyze_motion.setEnabled(bool(w.intent_controller.config))
        def analyze():w.intent_controller.animation_mode();w.intent_controller.start(False)
        self.analyze_motion.clicked.connect(analyze);controls.addWidget(self.analyze_motion)
        self.timeline=QPushButton('动作说明');self.timeline.clicked.connect(self.show_timeline);self.timeline.hide();controls.addWidget(self.timeline)
        layout.addLayout(controls);self.animation=self.dock('动画','animation',content)

    def make_toolbar(self,w):
        bar=QToolBar('创作');bar.setObjectName('creationToolbar');bar.setMovable(False);w.addToolBar(bar)
        self.group=QButtonGroup(w);self.group.setExclusive(True);self.modes=[]
        for index,title in enumerate(('单张图片','动画')):
            b=QPushButton(title);b.setCheckable(True);b.setObjectName('modeCard');self.group.addButton(b,index);self.modes.append(b);bar.addWidget(b)
        self.group.idClicked.connect(w.generation_type.setCurrentIndex)
        w.generation_type.currentIndexChanged.connect(lambda index:self.modes[index].setChecked(True))
        self.modes[w.generation_type.currentIndex()].setChecked(True);bar.addSeparator()
        self.settings_button=QPushButton('创作设置',self.hidden);self.settings_button.clicked.connect(lambda:self.open_settings('image'))
        self.details.setParent(self.hidden)
        spacer=QWidget();spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);bar.addWidget(spacer)
        w.cancel_button.setText('取消');bar.addWidget(w.cancel_button);bar.addWidget(w.generate_button)
        w.assets_dialog.setWindowTitle('记录')
        w.menuBar().addAction('记录',w.open_assets)
        for title,key in [('生成','creation'),('画面','image'),('采样','sampling'),('连接','connection')]:
            w.menuBar().addAction(title,lambda checked=False,section=key:self.open_settings(section))
        w.menuBar().addAction('API',w.api_controller.open_settings)
        view=w.menuBar().addMenu('窗口')
        for dock in self.docks.values():view.addAction(dock.toggleViewAction())
        view.addSeparator();view.addAction('恢复默认布局',self.reset_layout);self.view_menu=view

    def reset_layout(self,checked=False,*,save=True):
        self._restored=False
        for dock in self.docks.values():
            dock.showNormal();dock.setFloating(False);self.workspace.removeDockWidget(dock)
        self.workspace.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,self.canvas)
        self.workspace.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.prompt_dock)
        self.workspace.splitDockWidget(self.prompt_dock,self.animation,Qt.Orientation.Vertical)
        self.workspace.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.settings)
        self.settings.hide();self.prompt_dock.raise_()
        self.workspace.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,self.task)
        for dock in (self.canvas,self.prompt_dock,self.animation,self.task):dock.show()
        QTimer.singleShot(0,lambda:self.fit_default(save))

    def fit_default(self,save=False):
        if self._restored:return
        self.workspace.resizeDocks([self.canvas,self.prompt_dock],[900,420],Qt.Orientation.Horizontal)
        self.workspace.resizeDocks([self.prompt_dock,self.animation],[480,240],Qt.Orientation.Vertical)
        self.workspace.resizeDocks([self.task],[54],Qt.Orientation.Vertical)
        if save:self.save_layout()

    def save_layout(self):
        write_json(self.data/'workspace-layout.json',dict(schema_version=1,state=bytes(self.workspace.saveState(1).toBase64()).decode('ascii')))

    def restore_layout(self):
        try:
            value=json.loads((self.data/'workspace-layout.json').read_text('utf-8'))
            if value['schema_version']==1 and isinstance(value['state'],str) and len(value['state'])<200000:
                self._restored=self.workspace.restoreState(QByteArray.fromBase64(value['state'].encode('ascii')),1)
        except (OSError,ValueError,KeyError,TypeError):pass

    def open_settings(self,key):
        if key in self.sections:self.tabs.setCurrentIndex(self.sections[key])
        self.settings.setWindowTitle({'creation':'生成','image':'画面','sampling':'采样','connection':'连接'}.get(key,'设置'))
        self.settings.setFloating(True);self.settings.resize(520,660);self.settings.show();self.settings.raise_()

    def refresh_reference(self):
        w=self.window;present=bool(w.reference_path)
        self.reference_thumb.setVisible(present);self.reference_name.setVisible(present)
        self.remove_reference.setEnabled(present);w.intent_controller.role.setVisible(present)
        self.reference_thumb.set_clickable(present)
        if present:
            self.reference_name.setText(w.reference_display_name or Path(w.reference_path).name)
            self.reference_thumb.setPixmap(QPixmap(str(w.reference_path)).scaled(44,44,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        else:self.reference_thumb.clear();self.reference_name.clear()

    def motion_changed(self):
        panel=self.window.video_controller.motion
        if panel.path and panel.preview_paths:
            self.window.video_controller.player.stop();self.window.animation_player.stop()
            self.window.sequence_preview.clear_sequence();self.reference_player.load(panel.preview_paths)
            self.window.image_save.setEnabled(False);self.window.image_reuse.setEnabled(False)
        else:
            self.reference_player.stop()
            if self.window.preview_role=='motion_reference':
                if self.window.reference_path:self.window.show_image(str(self.window.reference_path),role='reference')
                else:
                    self.window.preview.clear();self.window.preview.setText('拖入参考素材')
                    self.window.pixmap=QPixmap();self.window.preview_path=None;self.window.preview_role=None

    def show_plan(self,result):
        self.plan=result;self.prompt_dock.show();self.prompt_dock.raise_()
        self.timeline.setVisible(bool(result.get('reference_timeline') or result['plan']['timeline']))

    def show_timeline(self):
        if not self.plan:return
        dialog=QDialog(self.window);dialog.setWindowTitle('动作说明');dialog.resize(720,440);layout=QVBoxLayout(dialog)
        rows=self.plan.get('reference_timeline') or self.plan['plan']['timeline'];table=QTableWidget(len(rows),3)
        table.setHorizontalHeaderLabels(['开始 / 秒','结束 / 秒','动作']);table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i,row in enumerate(rows):
            for j,value in enumerate((row['start'],row['end'],row['description'])):table.setItem(i,j,QTableWidgetItem(str(value)))
        table.resizeRowsToContents();layout.addWidget(table);done=QPushButton('关闭');done.clicked.connect(dialog.close);layout.addWidget(done)
        self.timeline_dialog=dialog;dialog.show()
