"""Manual frame picking: nothing is extracted or saved until an export is chosen."""
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt,QSize,QTimer
from PySide6.QtGui import QPixmap,QIcon
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QSplitter,QWidget,QLabel,
    QListWidget,QListWidgetItem,QPushButton,QSlider,QSpinBox,QCheckBox,QFileDialog,QApplication)
from .transparent_preview import TransparentPreview
from .selected_frames import read_source,export_selection


class FrameSelectionDialog(QDialog):
    def __init__(self,window,manifest):
        super().__init__(window);self.window=window;self.manifest=Path(manifest).resolve()
        self.data,self.paths=read_source(self.manifest);self.index=0;self.busy=False;self.closed=False
        self.prepared={};self.prepared_key=None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowTitle('选帧与导出');self.resize(1080,780)
        layout=QVBoxLayout(self);split=QSplitter();layout.addWidget(split,1)
        left=QWidget();lv=QVBoxLayout(left);self.preview=TransparentPreview();self.preview.setMinimumSize(260,340)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.resized.connect(self.fit)
        lv.addWidget(self.preview,1);self.frame_label=QLabel();lv.addWidget(self.frame_label)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(0,len(self.paths)-1)
        self.slider.valueChanged.connect(self.seek);lv.addWidget(self.slider)
        controls=QHBoxLayout()
        for title,callback in [('播放完整动画',lambda:self.play(False)),('播放所选帧',lambda:self.play(True)),('选取此帧',self.pick_current)]:
            b=QPushButton(title);b.clicked.connect(callback);controls.addWidget(b)
        lv.addLayout(controls);split.addWidget(left)
        self.grid=QListWidget();self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust);self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setIconSize(QSize(96,128));self.grid.setGridSize(QSize(126,168));split.addWidget(self.grid)
        self.grid.itemClicked.connect(self.focus_item)
        for i in range(len(self.paths)):
            item=QListWidgetItem(f'第 {i+1} 帧');item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked);self.grid.addItem(item)
        self.grid.itemChanged.connect(self.selection_changed)
        row=QHBoxLayout();self.summary=QLabel();row.addWidget(self.summary,1)
        self.seed=self.data.get('seed',self.data.get('params',{}).get('seed'))
        self.copy_seed=QPushButton('复制种子');self.copy_seed.setEnabled(isinstance(self.seed,int) and self.seed>=0)
        self.copy_seed.clicked.connect(lambda:QApplication.clipboard().setText(str(self.seed)))
        row.addWidget(self.copy_seed)
        all_button=QPushButton('全选');all_button.clicked.connect(lambda:self.check_all(True));row.addWidget(all_button)
        clear=QPushButton('清空');clear.clicked.connect(lambda:self.check_all(False));row.addWidget(clear);layout.addLayout(row)
        options=QHBoxLayout();options.addWidget(QLabel('所选帧播放 FPS'))
        self.fps=QSpinBox();self.fps.setRange(1,60);self.fps.setValue(8);options.addWidget(self.fps)
        options.addWidget(QLabel('精灵图列数'));self.columns=QSpinBox();self.columns.setRange(1,16);self.columns.setValue(4);options.addWidget(self.columns)
        self.transparent=QCheckBox('透明背景');self.transparent.setChecked(True);options.addWidget(self.transparent)
        self.loop=QCheckBox('循环播放');self.loop.setChecked(True);options.addWidget(self.loop);options.addStretch();layout.addLayout(options)
        self.status=QLabel()
        self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();self.sheet_button=QPushButton('导出精灵图…');self.png_button=QPushButton('导出所选 PNG…')
        self.sheet_button.clicked.connect(lambda:self.export('sheet'));self.png_button.clicked.connect(lambda:self.export('pngs'))
        buttons.addWidget(self.sheet_button);buttons.addWidget(self.png_button)
        close=QPushButton('关闭');close.clicked.connect(self.close);buttons.addWidget(close);layout.addLayout(buttons)
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.playback=[];self.play_position=0
        self.slider.sliderPressed.connect(self.timer.stop)
        self.thumbnails=QTimer(self);self.thumbnails.setInterval(15);self.thumb_index=0
        self.thumbnails.timeout.connect(self.load_thumbnails);self.thumbnails.start()
        self.pixmap=QPixmap();self.seek(0);self.selection_changed()

    def selected(self):return [i for i in range(self.grid.count()) if self.grid.item(i).checkState()==Qt.CheckState.Checked]

    def seek(self,index):
        self.index=index;self.slider.blockSignals(True);self.slider.setValue(index);self.slider.blockSignals(False)
        self.pixmap=QPixmap(str(self.paths[index]));self.fit()
        self.grid.setCurrentRow(index);self.grid.scrollToItem(self.grid.item(index))
        self.frame_label.setText(f'第 {index+1} / {len(self.paths)} 帧 · {index/float(self.data["fps"]):.2f} 秒')

    def fit(self):
        if hasattr(self,'pixmap') and not self.pixmap.isNull():
            self.preview.setPixmap(self.pixmap.scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def load_thumbnails(self):
        for _ in range(4):
            if self.thumb_index==len(self.paths):self.thumbnails.stop();return
            i=self.thumb_index;pixmap=QPixmap(str(self.paths[i]))
            self.grid.item(i).setIcon(QIcon(pixmap.scaled(96,128,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)))
            self.thumb_index+=1

    def focus_item(self,item):self.timer.stop();self.seek(self.grid.row(item))

    def pick_current(self):
        self.timer.stop();self.grid.item(self.index).setCheckState(Qt.CheckState.Checked)

    def check_all(self,checked):
        self.grid.blockSignals(True)
        for i in range(self.grid.count()):self.grid.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.grid.blockSignals(False);self.selection_changed()

    def selection_changed(self,*_):
        count=len(self.selected())
        self.summary.setText(f'已选 {count} / {len(self.paths)} 帧')
        for button in (self.sheet_button,self.png_button):button.setEnabled(bool(count) and not self.busy)

    def play(self,selected):
        if self.timer.isActive():self.timer.stop();return
        self.playback=self.selected() if selected else list(range(len(self.paths)))
        if not self.playback:self.status.setText('请先勾选需要播放的帧。');return
        self.play_position=0;self.seek(self.playback[0])
        rate=self.fps.value() if selected else float(self.data['fps']);self.timer.start(max(1,round(1000/rate)))

    def advance(self):
        if self.play_position==len(self.playback)-1 and not self.loop.isChecked():self.timer.stop();return
        self.play_position=(self.play_position+1)%len(self.playback);self.seek(self.playback[self.play_position])

    def export(self,kind):
        w=self.window
        if self.busy or w.current or w.preparing or w.cache_busy:self.status.setText('请等当前任务结束后再导出。');return
        indices=self.selected()
        if not indices:self.status.setText('请先选取至少一帧。');return
        if kind=='sheet':
            path,_=QFileDialog.getSaveFileName(self,'保存精灵图与JSON说明','sprite_sheet.png','PNG (*.png)')
            if path:path=str(Path(path).with_suffix('.png'))
        else:path=QFileDialog.getExistingDirectory(self,'选择PNG保存目录（将创建独立素材文件夹）')
        if not path:return
        try:
            target=w.cache_store.validate_export(path)
            if self.transparent.isChecked():
                from .background import model_file
                if not model_file().is_file():raise ValueError('透明模型尚未安装，请取消透明背景选项。')
        except (OSError,ValueError) as exc:self.status.setText(str(exc));return
        self.timer.stop();self.busy=True;self.selection_changed()
        folder=w.api_controller.data/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
        w.preparing=True;w.importing_folder=folder;w.importing_source=str(self.manifest)
        w.prepare_cancel.clear();self.cancel=w.prepare_cancel;w.task_display.start();w.progress.setRange(0,0)
        fps,columns,matte,loop=self.fps.value(),self.columns.value(),self.transparent.isChecked(),self.loop.isChecked()
        key=(tuple(indices),matte,tuple((self.paths[i].stat().st_mtime_ns,self.paths[i].stat().st_size) for i in indices))
        prepared=self.prepared.copy() if key==self.prepared_key else {}
        def event(event,data):
            if event=='selection_stage':
                w.status.setText(data['message'])
                if not self.closed:self.status.setText(data['message'])
            elif event=='selection_progress':
                w.progress.setRange(0,100);w.progress.setValue(round(95*data['value']/data['max']))
            elif event in ('result','error','cancelled'):
                w.preparing=False;w.importing_folder=None;w.importing_source=None;self.busy=False
                status={'result':'completed','error':'failed','cancelled':'cancelled'}[event]
                w.task_display.finish(status);w.progress.setRange(0,100);w.progress.setValue(100 if event=='result' else 0)
                if event=='result':
                    self.prepared_key=key
                    self.prepared={i:Path(data['manifest']).parent/f'frame_{n:03d}.png' for n,i in enumerate(indices)}
                    w.cache_store.record_save(data['output'],kind,data['manifest']);w.load_gallery()
                    if not self.closed:w.animation_player.load(data['manifest'])
                    message='已导出 '+str(len(indices))+' 帧：'+data['output']
                else:message='导出未完成：'+str(data)
                w.status.setText(message)
                if not self.closed:self.status.setText(message);self.selection_changed()
                QTimer.singleShot(0,w.start_next)
        w.launch(lambda emit:export_selection(self.manifest,indices,folder,target,kind,fps,columns,matte,loop,self.cancel,emit,prepared=prepared),event)

    def closeEvent(self,event):
        self.closed=True;self.timer.stop();self.thumbnails.stop()
        if self.busy:self.cancel.set()
        if getattr(self.window,'frame_selection_dialog',None) is self:self.window.frame_selection_dialog=None
        super().closeEvent(event)


def open_selection(window,manifest):
    if window.current or window.preparing or window.cache_busy:
        window.status.setText('请等当前任务结束后再选帧。');return
    existing=getattr(window,'frame_selection_dialog',None)
    if existing:existing.raise_();return
    try:
        dialog=FrameSelectionDialog(window,manifest);window.frame_selection_dialog=dialog;dialog.show()
    except (OSError,ValueError,KeyError) as exc:window.add_chat('软件','无法打开选帧窗口：'+str(exc))
