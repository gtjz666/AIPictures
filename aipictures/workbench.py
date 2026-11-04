"""Fixed, resizable workspace: canvas and task left, tabbed tools right."""
import json
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QButtonGroup,QDialog,QTabWidget,QScrollArea,
    QSizePolicy,QToolBar,QSplitter,QSlider,QCheckBox,QComboBox)
from .storage import write_json
from .transparent_preview import TransparentPreview


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

    def load(self,paths,fps=24.):
        self.timer.stop();self.paths=[Path(p) for p in paths];self.index=0;self.fps=fps
        self.slider.blockSignals(True);self.slider.setRange(0,max(0,len(self.paths)-1));self.slider.setValue(0);self.slider.blockSignals(False)
        self.seek(0);self.play.setText('播放');self.show()

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
        prompt_layout=self.prompts.layout();self.prompt_splitter=QSplitter(Qt.Orientation.Vertical)
        self.prompt_splitter.setChildrenCollapsible(False)
        while prompt_layout.count():
            item=prompt_layout.takeAt(0)
            if item.widget():self.prompt_splitter.addWidget(item.widget())
        prompt_layout.addWidget(self.prompt_splitter)
        self.legacy_root=w.takeCentralWidget();self.legacy_root.hide()
        self.legacy_root.setParent(self.hidden)
        w.removeDockWidget(w.diagnostics);w.diagnostics.setParent(self.hidden);w.output_shortcut.setEnabled(False)
        w.tabs.setParent(w);w.setCentralWidget(w.tabs)
        old_page=w.tabs.widget(0);w.tabs.removeTab(0);old_page.setParent(self.hidden)
        self.workspace=QSplitter(Qt.Orientation.Horizontal);self.workspace.setChildrenCollapsible(False)
        self.canvas=QWidget();cv=QVBoxLayout(self.canvas);cv.setContentsMargins(6,6,6,6)
        self.right_tabs=QTabWidget();self.right_tabs.setMovable(False);self.right_tabs.setTabsClosable(False)
        self.workspace.addWidget(self.canvas);self.workspace.addWidget(self.right_tabs)
        self.workspace.setStretchFactor(0,3);self.workspace.setStretchFactor(1,1)
        w.tabs.insertTab(0,self.workspace,'创作');w.tabs.setCurrentIndex(0)
        for control in (w.creation_summary,w.reference_label,w.context_label,w.intent_hint,w.style_status,w.seed_notice,w.caption):
            control.setParent(self.hidden)
        w.preview.setText('拖入参考素材');w.preview.setMinimumSize(320,240)
        # Splitter/tab/footer changes resize the preview without resizing the main window.
        w.preview.resized.connect(w.fit_preview)
        w.preview.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        w.sequence_preview.sheet.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        w.sequence_preview.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        self.make_reference(w,cv)
        cv.addWidget(w.sequence_preview,1)
        from .reference_asset import SourceCaption
        self.source_note=SourceCaption()
        actions=QHBoxLayout();actions.addWidget(self.source_note,1);actions.addWidget(w.image_save);actions.addWidget(w.image_reuse);cv.addLayout(actions)
        self.reference_player=ReferencePlayback(w);cv.addWidget(self.reference_player)
        cv.addWidget(w.animation_player);cv.addWidget(w.video_controller.player)
        w.image_save.setEnabled(False);w.image_reuse.setEnabled(False)
        self.make_settings(w);self.make_prompts(w);self.make_animation(w)
        self.task=QWidget();task_layout=QVBoxLayout(self.task);task_layout.setContentsMargins(0,3,0,0)
        task_layout.setSpacing(2);task_layout.addWidget(QLabel('当前任务'));task_layout.addWidget(w.task_display)
        cv.addWidget(self.task)
        self.make_toolbar(w);self.reset_layout(save=False)
        w.generation_type.hide();w.animation_action.setCurrentIndex(w.animation_action.findData('custom'))
        w.positive.setMinimumHeight(80);w.negative.setMinimumHeight(64)
        w.positive.setMaximumHeight(16777215);w.negative.setMaximumHeight(16777215)
        w.intent_controller.panel.setParent(self.hidden);w.intent_controller.input.hide()
        w.video_controller.motion.changed.connect(self.motion_changed)
        self.refresh_reference();QTimer.singleShot(0,self.restore_layout)

    @staticmethod
    def scroll_page(content):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);return scroll

    def make_settings(self,w):
        content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(6,6,6,6)
        self.tabs=QTabWidget();layout.addWidget(self.tabs);self.sections={}
        self.tabs.tabBar().hide()
        for key,title in [('creation','生成'),('image','画面'),('sampling','采样'),('connection','连接')]:
            scroll=w.settings_dialogs[key].findChild(QScrollArea)
            if scroll:
                page=scroll.takeWidget();container=QScrollArea();container.setWidgetResizable(True);container.setWidget(page)
                self.sections[key]=self.tabs.addTab(container,title)
        self.settings=QDialog(w);self.settings.setWindowTitle('设置');self.settings.resize(520,660)
        QVBoxLayout(self.settings).addWidget(content)
        for button in w.settings_buttons.values():button.setParent(self.hidden)
        w.api_controller.button.setParent(self.hidden);w.api_controller.summary.setParent(self.hidden)

    def make_reference(self,w,layout):
        c=w.intent_controller
        from .reference_asset import ReferenceAsset
        self.reference_item=ReferenceAsset('参考图');self.reference_item.clicked.connect(self.show_reference)
        self.reference_item.closed.connect(lambda:self.close_asset('image'))
        self.reference_thumb=self.reference_item.thumb
        self.motion_item=ReferenceAsset('参考动画');self.motion_item.clicked.connect(lambda:self.show_motion_reference(play=True))
        self.motion_item.closed.connect(lambda:self.close_asset('motion'))
        self.reference_items=QWidget();items=QHBoxLayout(self.reference_items);items.setContentsMargins(0,0,0,0)
        items.addWidget(self.reference_item);items.addWidget(self.motion_item);items.addStretch(1)
        reference=QHBoxLayout();reference.addWidget(self.reference_items,1)
        reference.addWidget(w.attach_reference_button)
        w.attach_reference_button.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Preferred)
        remove=QPushButton('移除',self.hidden);remove.clicked.connect(self.remove_asset)
        self.remove_reference=remove
        remove.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Preferred)
        c.role.setItemText(0,'角色 / 外观');c.role.setItemText(1,'画风 / 布局');c.role.setItemText(2,'编辑底图')
        c.role.setMaximumWidth(180);reference.insertWidget(1,c.role);layout.addLayout(reference)

    def make_prompts(self,w):
        c=w.intent_controller;content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(8,6,8,6)
        layout.addWidget(self.prompts,1)
        c.organize.setText('自动生成提示词');layout.addWidget(c.organize);layout.addWidget(c.note)
        self.prompt_page=self.scroll_page(content);self.right_tabs.addTab(self.prompt_page,'提示词')

    def make_animation(self,w):
        content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(8,6,8,6)
        self.animation_header=QWidget();header=QVBoxLayout(self.animation_header);header.setContentsMargins(0,0,0,0)
        self.animation_header.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        w.animation_action_label.setParent(self.hidden);w.animation_action.setParent(self.hidden)
        self.creation_kind=QComboBox();self.creation_kind.addItem('动画素材','sprite');self.creation_kind.addItem('长视频（暂未开放）','long_video')
        self.creation_kind.model().item(1).setEnabled(False)
        self.creation_kind.model().item(1).setToolTip('分段衔接尚未完成整段验证。')
        kind_row=QHBoxLayout();kind_row.addWidget(QLabel('制作类型'));kind_row.addWidget(self.creation_kind,1);kind_row.addWidget(w.video_controller.motion.frame_rate_row);header.addLayout(kind_row)
        w.video_controller.motion.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        w.video_controller.motion.asset_header.setParent(self.hidden)
        panel=w.video_controller.motion
        for button in (panel.add,panel.add_frames,panel.play,panel.remove):button.setParent(self.hidden)
        panel.range_button.setParent(self.hidden)
        left=QWidget();self.motion_selection=left;selection=QVBoxLayout(left);selection.setContentsMargins(0,0,0,0)
        selection.addWidget(panel.repeat);selection.addWidget(panel.start_note);selection.addWidget(panel.range_slider)
        self.analyze_motion=QPushButton('分析动作');self.analyze_motion.setEnabled(bool(w.intent_controller.config))
        self.analyze_motion.setMinimumHeight(66)
        def analyze():
            w.intent_controller.animation_mode()
            w.intent_controller.start(False,frame_only=bool(panel.is_frames() and self.analysis_tabs.currentIndex()==1))
        self.analyze_motion.clicked.connect(analyze)
        controls=QHBoxLayout();controls.addWidget(left,1);controls.addWidget(self.analyze_motion);header.addLayout(controls)
        panel.setParent(self.hidden)
        self.reference_player.loop.hide();self.reference_player.loop.setChecked(panel.repeat.isChecked())
        panel.repeat.toggled.connect(self.reference_player.loop.setChecked)
        taken=w.walk_form.takeRow(w.video_controller.seconds)
        if taken.labelItem:taken.labelItem.widget().hide()
        duration=QHBoxLayout();duration.addWidget(QLabel('时长 / 秒'));duration.addWidget(w.video_controller.seconds,1);header.addLayout(duration)
        layout.addWidget(self.animation_header,0,Qt.AlignmentFlag.AlignTop)
        from .animation_timeline import ActionTimeline
        # The empty region remains present before analysis and after removing a
        # source; hiding the editor must never stretch the header's inner rows.
        self.timeline_region=QWidget();self.timeline_region.setMinimumHeight(200)
        region=QVBoxLayout(self.timeline_region);region.setContentsMargins(0,0,0,0)
        self.analysis_tabs=QTabWidget();region.addWidget(self.analysis_tabs,1)
        page=QWidget();page_layout=QVBoxLayout(page);page_layout.setContentsMargins(0,0,0,0)
        self.timeline=ActionTimeline(w);page_layout.addWidget(self.timeline)
        self.analysis_tabs.addTab(page,'动作说明')
        from .frame_review import FrameReview
        self.frame_review=FrameReview(panel);self.analysis_tabs.addTab(self.frame_review,'帧内容');self.analysis_tabs.setTabVisible(1,False)
        self.analysis_tabs.tabBar().hide()
        layout.addWidget(self.timeline_region,1)
        self.animation=self.scroll_page(content);self.right_tabs.addTab(self.animation,'动画')

    def make_toolbar(self,w):
        bar=QToolBar('创作');bar.setObjectName('creationToolbar');bar.setMovable(False);w.addToolBar(bar)
        self.group=QButtonGroup(w);self.group.setExclusive(True);self.modes=[]
        for index,title in enumerate(('单张图片','动画')):
            b=QPushButton(title);b.setCheckable(True);b.setObjectName('modeCard');self.group.addButton(b,index);self.modes.append(b);bar.addWidget(b)
        self.group.idClicked.connect(w.generation_type.setCurrentIndex)
        w.generation_type.currentIndexChanged.connect(lambda index:self.modes[index].setChecked(True))
        self.modes[w.generation_type.currentIndex()].setChecked(True);bar.addSeparator()
        self.settings_button=QPushButton('创作设置',self.hidden);self.settings_button.clicked.connect(lambda:self.open_settings('image'))
        spacer=QWidget();spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);bar.addWidget(spacer)
        w.cancel_button.setText('取消');bar.addWidget(w.cancel_button);bar.addWidget(w.generate_button)
        w.assets_dialog.setWindowTitle('记录')
        w.menuBar().addAction('记录',w.open_assets)
        for title,key in [('画面','image'),('采样','sampling'),('连接','connection')]:
            w.menuBar().addAction(title,lambda checked=False,section=key:self.open_settings(section))
        w.menuBar().addAction('API',w.api_controller.open_settings)
        view=w.menuBar().addMenu('窗口')
        view.addAction('恢复默认布局',self.reset_layout);self.view_menu=view

    def reset_layout(self,checked=False,*,save=True):
        self._restored=False
        self.right_tabs.setCurrentIndex(0)
        QTimer.singleShot(0,lambda:self.fit_default(save))

    def fit_default(self,save=False):
        if self._restored:return
        self.workspace.setSizes([900,420]);self.prompt_splitter.setSizes([300,200])
        if save:self.save_layout()

    @staticmethod
    def valid_sizes(value):
        return (isinstance(value,list) and len(value)==2 and
                all(type(n) is int and 0<n<=100000 for n in value))

    def save_layout(self):
        columns=self.workspace.sizes();editors=self.prompt_splitter.sizes()
        write_json(self.data/'workspace-layout.json',dict(schema_version=2,
            columns=columns if self.valid_sizes(columns) else [900,420],
            editors=editors if self.valid_sizes(editors) else [300,200],right_tab=self.right_tabs.currentIndex()))

    def restore_layout(self):
        try:
            value=json.loads((self.data/'workspace-layout.json').read_text('utf-8'))
            if (value['schema_version']==2 and self.valid_sizes(value.get('columns')) and
                self.valid_sizes(value.get('editors')) and type(value.get('right_tab')) is int and value['right_tab'] in (0,1)):
                self.workspace.setSizes(value['columns']);self.prompt_splitter.setSizes(value['editors'])
                self.right_tabs.setCurrentIndex(value['right_tab']);self._restored=True
        except (OSError,ValueError,KeyError,TypeError):pass

    def open_settings(self,key):
        if key in self.sections:self.tabs.setCurrentIndex(self.sections[key])
        self.settings.setWindowTitle({'creation':'生成','image':'画面','sampling':'采样','connection':'连接'}.get(key,'设置'))
        self.settings.show();self.settings.raise_();self.settings.activateWindow()

    def refresh_reference(self):
        w=self.window;present=bool(w.reference_path)
        self.reference_item.setVisible(present);w.intent_controller.role.setVisible(present)
        if present:
            self.reference_item.set_source(str(w.reference_path))
        self.refresh_motion_asset();self.refresh_asset_selection()
        if not present and w.preview_role is None and w.video_controller.motion.path:self.show_motion_reference()

    def refresh_motion_asset(self):
        panel=self.window.video_controller.motion;present=bool(panel.path and panel.preview_paths)
        self.motion_item.setVisible(present)
        if present:self.motion_item.set_source(panel.preview_paths[0])
        self.remove_reference.setEnabled(bool(self.window.reference_path or present))

    def refresh_asset_selection(self):
        self.reference_item.setChecked(self.window.preview_role=='reference' and bool(self.window.reference_path))
        self.motion_item.setChecked(self.window.preview_role=='motion_reference' and bool(self.window.video_controller.motion.path))
        w=self.window;hint=''
        if self.reference_item.isChecked():hint=w.reference_display_name or Path(w.reference_path).name
        elif self.motion_item.isChecked():hint=w.video_controller.motion.meta['name']
        self.source_note.set_hint(hint)

    def show_reference(self):
        if self.window.reference_path:self.window.show_image(str(self.window.reference_path),role='reference')

    def show_motion_reference(self,*,play=False,position=0):
        panel=self.window.video_controller.motion
        if not panel.path or not panel.preview_paths:return
        w=self.window;w.video_controller.player.stop();w.animation_player.stop()
        w.sequence_preview.clear_sequence();self.reference_player.load(panel.preview_paths,panel.preview_fps)
        self.reference_player.slider.setValue(min(position,len(panel.preview_paths)-1))
        w.image_save.setEnabled(False);w.image_reuse.setEnabled(False)
        if play:self.reference_player.toggle()
        QTimer.singleShot(0,w.fit_preview)

    def remove_asset(self):
        if self.motion_item.isChecked() or not self.window.reference_path:self.window.video_controller.motion.clear()
        else:self.window.clear_reference()

    def close_asset(self,kind:str):
        if self.window.preparing:
            self.window.status.setText('请等待当前素材准备或识别结束后移除。');return
        if kind=='motion':self.window.video_controller.motion.clear()
        else:self.window.clear_reference()

    def motion_changed(self):
        panel=self.window.video_controller.motion
        self.refresh_motion_asset()
        self.analysis_tabs.setTabVisible(1,panel.is_frames())
        self.analysis_tabs.tabBar().setVisible(panel.is_frames())
        self.analysis_tabs.setCurrentIndex(1 if panel.is_frames() else 0)
        if panel.path and panel.preview_paths:
            self.right_tabs.setCurrentIndex(1)
            self.show_motion_reference()
        else:
            self.reference_player.stop()
            if self.window.preview_role=='motion_reference':
                if self.window.reference_path:self.window.show_image(str(self.window.reference_path),role='reference')
                else:
                    self.window.preview.clear();self.window.preview.setText('拖入参考素材')
                    self.window.pixmap=QPixmap();self.window.preview_path=None;self.window.preview_role=None
        self.refresh_asset_selection()

    def show_plan(self,result):
        self.plan=result
        self.timeline.load_plan(result)
        self.analysis_tabs.setCurrentIndex(0)

    def show_frame_analysis(self,result):
        self.frame_review.add_result(result);self.analysis_tabs.setCurrentIndex(1)

    def show_timeline(self):
        self.right_tabs.setCurrentIndex(1)
        if self.plan:self.timeline.show();self.timeline.table.setFocus()
