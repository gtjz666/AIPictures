"""Preview every source frame at source FPS; extraction is an explicit separate action."""
import json
import shutil
from pathlib import Path

from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget,QHBoxLayout,QPushButton,QSlider,QLabel,QFileDialog


class VideoPreview(QWidget):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.manifest=None;self.frames=[];self.source=None
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0)
        self.play=QPushButton('播放');self.play.clicked.connect(self.toggle);row.addWidget(self.play)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.valueChanged.connect(self.seek);row.addWidget(self.slider,1)
        self.label=QLabel();row.addWidget(self.label)
        save=QPushButton('保存完整动画…');save.clicked.connect(self.save);row.addWidget(save)
        self.extract=QPushButton('处理为动画帧…');self.extract.clicked.connect(self.split);row.addWidget(self.extract)
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.hide()

    def load(self,path):
        self.stop();self.manifest=Path(path);data=json.loads(self.manifest.read_text('utf-8'))
        if data['status']!='completed':raise ValueError('动画尚未生成完成。')
        self.frames=[self.manifest.parent/f['image'] for f in data['frames']]
        if not self.frames or not all(p.is_file() for p in self.frames):raise ValueError('完整动画预览文件缺失。')
        self.source=Path(data['source_video']);self.fps=float(data['fps']);self.index=0
        self.window.animation_player.stop();self.window.sequence_preview.clear_sequence()
        self.slider.setRange(0,len(self.frames)-1);self.seek(0);self.show()
        self.play.setText('暂停');self.timer.start(max(1,round(1000/self.fps)))

    def seek(self,index):
        if not self.frames:return
        self.index=index;w=self.window;w.pixmap=QPixmap(str(self.frames[index]))
        w.output=None;w.preview_path=str(self.frames[index]);w.preview_role='video';w.preview.set_clickable(False)
        w.image_save.hide();w.image_reuse.hide()
        w.caption.setText('完整动画预览 · 满意后点击“处理为动画帧”');w.fit_preview()
        self.label.setText(f'{index+1}/{len(self.frames)} · {index/self.fps:.2f}s')

    def advance(self):
        if self.index==len(self.frames)-1:self.timer.stop();self.play.setText('重播');return
        self.slider.setValue(self.index+1)

    def stop(self):
        self.timer.stop();self.hide()
        self.window.image_save.show();self.window.image_reuse.show()

    def toggle(self):
        if self.timer.isActive():self.timer.stop();self.play.setText('播放')
        elif self.frames:
            if self.index==len(self.frames)-1:self.slider.setValue(0)
            self.timer.start(max(1,round(1000/self.fps)));self.play.setText('暂停')

    def reset(self):
        self.stop();self.manifest=None;self.source=None;self.frames=[]

    def split(self):
        if self.manifest and self.source.is_file():
            self.timer.stop();self.play.setText('播放')
            from .video_import_dialog import open_import
            open_import(self.window,self.source)

    def save(self):
        if not self.manifest or not self.source.is_file():return
        path,_=QFileDialog.getSaveFileName(self,'保存完整动画','animation'+self.source.suffix,'动画 (*'+self.source.suffix+')')
        if path:
            try:
                target=self.window.cache_store.validate_export(path)
                if target.resolve()==self.source.resolve():raise ValueError('请选择缓存目录以外的新保存位置。')
                shutil.copyfile(self.source,target)
                self.window.cache_store.record_save(target,'video',self.manifest);self.window.load_gallery()
            except (OSError,ValueError) as exc:self.window.add_chat('软件','保存动画失败：'+str(exc))
