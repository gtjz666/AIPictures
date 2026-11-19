"""Manual frame picking: nothing is extracted or saved until an export is chosen."""
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt,QSize,QTimer,QUrl
from PySide6.QtGui import QImage,QPixmap,QIcon,QDesktopServices
from shiboken6 import isValid
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QSplitter,QWidget,QLabel,
    QListWidget,QListWidgetItem,QPushButton,QSlider,QSpinBox,QCheckBox,QFileDialog,QApplication)
from .transparent_preview import TransparentPreview
from .selected_frames import FrameSource,export_selection


class FrameSelectionDialog(QDialog):
    def __init__(self,window,manifest):
        super().__init__(window);self.window=window;self.manifest=Path(manifest).resolve()
        self.source=FrameSource(self.manifest,original=True)
        self.data=self.source.data;self.index=0;self.busy=False;self.closed=False
        self.exported_manifest=None
        self.prepared={}
        self.prepared_key=None
        self.source_manifest=Path(self.data.get('source_manifest') or self.manifest)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.finished.connect(self.on_finished)
        self.setWindowTitle('选帧与导出');self.resize(1080,780)
        layout=QVBoxLayout(self);split=QSplitter();layout.addWidget(split,1)
        left=QWidget();lv=QVBoxLayout(left);self.preview=TransparentPreview();self.preview.setMinimumSize(260,340)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.resized.connect(self.fit)
        lv.addWidget(self.preview,1);self.frame_label=QLabel();lv.addWidget(self.frame_label)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(0,self.source.count-1)
        self.slider.valueChanged.connect(self.seek);lv.addWidget(self.slider)
        controls=QHBoxLayout()
        for title,callback in [('播放完整动画',lambda:self.play(False)),('播放所选帧',lambda:self.play(True)),('选取此帧',self.pick_current)]:
            b=QPushButton(title);b.clicked.connect(callback);controls.addWidget(b)
        lv.addLayout(controls);split.addWidget(left)
        self.grid=QListWidget();self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust);self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setIconSize(QSize(96,128));self.grid.setGridSize(QSize(126,168));split.addWidget(self.grid)
        self.grid.itemClicked.connect(self.focus_item)
        for i in range(self.source.count):
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
        self.status=QLabel('预览原始画面。勾选透明背景后，导出时只处理所选帧。')
        self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();self.clip_button=QPushButton('导出动画…');self.sheet_button=QPushButton('导出精灵图…');self.png_button=QPushButton('导出所选 PNG…')
        self.clip_button.clicked.connect(lambda:self.export('clip'));buttons.addWidget(self.clip_button)
        self.sheet_button.clicked.connect(lambda:self.export('sheet'));self.png_button.clicked.connect(lambda:self.export('pngs'))
        buttons.addWidget(self.sheet_button);buttons.addWidget(self.png_button)
        self.output_path=None
        self.reveal=QPushButton('打开导出位置');self.reveal.setEnabled(False);self.reveal.clicked.connect(self.reveal_export);buttons.addWidget(self.reveal)
        close=QPushButton('关闭');close.clicked.connect(self.close);buttons.addWidget(close);layout.addLayout(buttons)
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.playback=[];self.play_position=0
        self.slider.sliderPressed.connect(self.timer.stop)
        self.thumbnails=QTimer(self);self.thumbnails.setInterval(15);self.thumb_index=0
        self.thumbnails.timeout.connect(self.load_thumbnails);self.thumbnails.start()
        self.pixmap=QPixmap();self.seek(0);self.selection_changed()

    def pixmap_at(self,index,thumbnail=False):
        try:
            image=self.source.image(index)
            if thumbnail:image.thumbnail((96,128))
            raw=image.tobytes()
            return QPixmap.fromImage(QImage(raw,image.width,image.height,image.width*4,QImage.Format.Format_RGBA8888).copy())
        except (OSError,ValueError) as exc:
            self.status.setText('无法读取帧：'+str(exc))
            return QPixmap()

    def selected(self):return [i for i in range(self.grid.count()) if self.grid.item(i).checkState()==Qt.CheckState.Checked]

    def seek(self,index):
        self.index=index;self.slider.blockSignals(True);self.slider.setValue(index);self.slider.blockSignals(False)
        self.pixmap=self.pixmap_at(index);self.fit()
        self.grid.setCurrentRow(index);self.grid.scrollToItem(self.grid.item(index))
        self.frame_label.setText(f'第 {index+1} / {self.source.count} 帧 · {index/float(self.data["fps"]):.2f} 秒')

    def fit(self):
        if hasattr(self,'pixmap') and not self.pixmap.isNull():
            self.preview.setPixmap(self.pixmap.scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def load_thumbnails(self):
        for _ in range(4):
            if self.thumb_index==self.source.count:self.thumbnails.stop();return
            i=self.thumb_index
            self.grid.item(i).setIcon(QIcon(self.pixmap_at(i,thumbnail=True)))
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
        self.summary.setText(f'已选 {count} / {self.source.count} 帧')
        for button in (self.clip_button,self.sheet_button,self.png_button):button.setEnabled(bool(count) and not self.busy)

    def reveal_export(self):
        if self.output_path:
            folder=self.output_path if self.output_path.is_dir() else self.output_path.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def play(self,selected):
        if self.timer.isActive():self.timer.stop();return
        self.playback=self.selected() if selected else list(range(self.source.count))
        if not self.playback:self.status.setText('请先勾选需要播放的帧。');return
        self.play_position=0;self.seek(self.playback[0])
        rate=self.fps.value() if selected else float(self.data['fps']);self.timer.start(max(1,round(1000/rate)))

    def advance(self):
        if self.play_position==len(self.playback)-1 and not self.loop.isChecked():self.timer.stop();return
        self.play_position=(self.play_position+1)%len(self.playback);self.seek(self.playback[self.play_position])

    def export(self,kind):
        w=self.window
        if w.export_tasks.busy or w.cache_busy:self.status.setText('已有导出或缓存清理正在进行。');return
        indices=self.selected()
        if not indices:self.status.setText('请先选取至少一帧。');return
        if kind=='clip':
            path,_=QFileDialog.getSaveFileName(self,'保存动画文件','animation.zip','动画文件 (*.zip)')
            if path:path=str(Path(path).with_suffix('.zip'))
        elif kind=='sheet':
            path,_=QFileDialog.getSaveFileName(self,'保存精灵图与JSON说明','sprite_sheet.png','PNG (*.png)')
            if path:path=str(Path(path).with_suffix('.png'))
        else:path=QFileDialog.getExistingDirectory(self,'选择PNG保存目录（将创建独立素材文件夹）')
        if not path:return
        try:
            target=w.cache_store.validate_export(path)
        except (OSError,ValueError) as exc:self.status.setText(str(exc));return
        self.timer.stop();self.busy=True;self.selection_changed()
        folder=w.api_controller.data/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
        fps,columns,matte,loop=self.fps.value(),self.columns.value(),self.transparent.isChecked(),self.loop.isChecked()
        manifest=self.manifest
        key=(tuple(indices),matte)
        prepared=self.prepared.copy() if matte and key==self.prepared_key else {}
        previous_preview=w.video_controller.player.manifest
        def done(event,data):
            self.busy=False
            visible=not self.closed and isValid(self)
            if event=='result':
                self.exported_manifest=Path(data['manifest'])
                self.output_path=Path(data['output'])
                self.prepared_key=key
                self.prepared={index:self.exported_manifest.parent/f'frame_{position:03d}.png' for position,index in enumerate(indices)}
                w.cache_store.record_save(data['output'],kind,data['manifest']);w.load_gallery()
                if (visible and not w.current and previous_preview==manifest
                    and w.video_controller.player.manifest==manifest and w.preview_role=='video'):
                    w.animation_player.load(data['manifest'])
                message='已导出 '+str(len(indices))+' 帧：'+data['output']
            else:message='导出未完成：'+str(data)
            if visible:
                self.reveal.setEnabled(self.output_path is not None)
                self.status.setText(message);self.selection_changed()
        accepted=w.export_tasks.submit('导出动画帧', [manifest,self.source_manifest,self.source.native,folder,*self.source.paths,*self.source.processed,*prepared.values()],
            lambda cancel,emit:export_selection(manifest,indices,folder,target,kind,fps,columns,matte,loop,cancel,emit,prepared=prepared),
            done,popup=True)
        if accepted:self.status.setText(f'正在导出所选 {len(indices)} 帧…')
        else:
            self.busy=False;self.selection_changed()
            self.status.setText('已有导出或缓存清理正在进行。')

    def on_finished(self):
        self.closed=True;self.timer.stop();self.thumbnails.stop()
        if getattr(self.window,'frame_selection_dialog',None) is self:self.window.frame_selection_dialog=None


def open_selection(window,manifest):
    if window.cache_busy:return
    existing=getattr(window,'frame_selection_dialog',None)
    if existing and isValid(existing):
        if existing.manifest==Path(manifest).resolve():existing.raise_();existing.activateWindow();return existing
        existing.close()
    try:
        dialog=FrameSelectionDialog(window,manifest);window.frame_selection_dialog=dialog;dialog.show();return dialog
    except (OSError,ValueError,KeyError) as exc:window.add_chat('软件','无法打开选帧窗口：'+str(exc))
