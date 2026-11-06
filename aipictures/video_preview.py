"""Preview every source frame at source FPS; extraction is an explicit separate action."""
import json
import shutil
from pathlib import Path

from .playback_button import PlaybackButton
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QPixmap,QImage
from PySide6.QtWidgets import QWidget,QHBoxLayout,QPushButton,QSlider,QLabel,QFileDialog,QCheckBox,QMenu


class VideoPreview(QWidget):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.manifest=None;self.frames=[];self.source=None;self.rgb_source=None;self.count=0
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0)
        self.play=PlaybackButton();self.play.clicked.connect(self.toggle);row.addWidget(self.play)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.valueChanged.connect(self.seek);row.addWidget(self.slider,1)
        self.label=QLabel();row.addWidget(self.label)
        self.loop=QCheckBox('循环');self.loop.setChecked(True);row.addWidget(self.loop)
        self.extract=QPushButton('导出…');self.extract.clicked.connect(self.choose_export);row.addWidget(self.extract)
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance);self.hide()

    def load(self,path):
        self.stop();self.manifest=Path(path);data=json.loads(self.manifest.read_text('utf-8'))
        if data['status']!='completed':raise ValueError('动画尚未生成完成。')
        self.frames=[self.manifest.parent/f['image'] for f in data['frames']]
        self.rgb_source=Path(data['native_rgb_source']) if data.get('native_rgb_source') else None
        self.video_export_pending=data.get('video_export_pending',False)
        self.count=len(self.frames)
        if not self.frames and self.rgb_source:
            from .video_io import native_rgb_info
            native_count,_,_=native_rgb_info(self.rgb_source)
            self.count=int(data.get('frame_count',native_count))
            if not 1<=self.count<=native_count:raise ValueError('预览帧数超出原生动画范围。')
        if not self.count or not all(p.is_file() for p in self.frames):raise ValueError('完整动画预览文件缺失。')
        self.source=Path(data['source_video']) if data.get('source_video') else None
        self.fps=float(data['fps']);self.index=0
        from .seed_controls import from_folder
        from_folder(self.window,self.manifest.parent)
        self.window.animation_player.stop();self.window.sequence_preview.clear_sequence()
        self.slider.setRange(0,self.count-1);self.seek(0);self.show()
        self.play.set_playing(True);self.timer.start(max(1,round(1000/self.fps)))

    def seek(self,index):
        if not 0<=index<self.count:return
        self.index=index;w=self.window
        if self.frames:
            w.pixmap=QPixmap(str(self.frames[index]));w.preview_path=str(self.frames[index])
        else:
            from .video_io import native_rgb_image
            image=native_rgb_image(self.rgb_source,index);raw=image.tobytes()
            w.pixmap=QPixmap.fromImage(QImage(raw,image.width,image.height,image.width*3,QImage.Format.Format_RGB888).copy())
            w.preview_path=str(self.rgb_source)
        w.output=None;w.preview_role='video';w.preview.set_clickable(False)
        w.image_save.hide();w.image_reuse.hide()
        w.caption.setText('完整动画循环预览 · 点击“选帧与导出”勾选需要的帧');w.fit_preview()
        self.label.setText(f'{index+1}/{self.count} · {index/self.fps:.2f}s')

    def advance(self):
        if not self.window.preview.isVisible() or self.window.isMinimized():
            self.timer.stop();self.play.set_playing(False);return
        if not self.loop.isChecked() and self.index==self.count-1:self.timer.stop();self.play.set_playing(False,replay=True);return
        self.slider.setValue((self.index+1)%self.count)

    def stop(self):
        self.timer.stop();self.play.set_playing(False);self.hide()
        self.window.image_save.show();self.window.image_reuse.show()

    def toggle(self):
        if self.timer.isActive():self.timer.stop();self.play.set_playing(False)
        elif self.count:
            if self.index==self.count-1:self.slider.setValue(0)
            self.timer.start(max(1,round(1000/self.fps)));self.play.set_playing(True)

    def reset(self):
        self.stop();self.manifest=None;self.source=None;self.frames=[];self.rgb_source=None;self.count=0

    def choose_export(self):
        menu=QMenu(self)
        menu.addAction('完整视频…',self.save)
        menu.addAction('动画帧／精灵图…',self.split)
        menu.exec(self.extract.mapToGlobal(self.extract.rect().bottomLeft()))

    def process_export(self,action,done):
        w=self.window
        if w.current or w.pending or w.preparing or w.cache_busy:
            w.status.setText('请等当前任务结束后再导出。');return
        self.timer.stop();self.play.set_playing(False)
        w.preparing=True;w.importing_folder=self.manifest.parent;w.prepare_cancel.clear()
        w.task_display.start();w.progress.setRange(0,0);w.status.setText('正在准备导出…')
        def event(kind,data):
            if kind=='video_export_progress':
                w.progress.setRange(0,100);w.progress.setValue(round(95*data['value']/data['max']))
            elif kind=='video_stage':w.status.setText(data['message'])
            elif kind in ('result','error','cancelled'):
                from .engine import Cancelled
                cancelled=kind=='cancelled' or isinstance(data,Cancelled)
                w.preparing=False;w.importing_folder=None
                w.task_display.finish('completed' if kind=='result' else 'cancelled' if cancelled else 'failed')
                w.progress.setRange(0,100);w.progress.setValue(100 if kind=='result' else 0)
                if kind=='result':done()
                else:w.add_chat('软件','导出未完成，原动画保留：'+str(data))
                QTimer.singleShot(0,w.start_next)
        w.launch(lambda emit:action(w.prepare_cancel,emit),event)

    def split(self):
        if self.manifest:
            self.timer.stop();self.play.set_playing(False)
            from .frame_selection import open_selection
            manifest=self.manifest
            if self.frames:open_selection(self.window,manifest)
            else:
                from .video_io import prepare_export_frames
                self.process_export(lambda cancel,emit:prepare_export_frames(manifest,cancel,emit),
                                    lambda:open_selection(self.window,manifest))

    def save(self):
        if not self.manifest:return
        suffix=self.source.suffix if self.source and not self.rgb_source else '.mp4'
        path,_=QFileDialog.getSaveFileName(self,'保存完整动画','animation'+suffix,'动画 (*'+suffix+')')
        if path:
            try:
                target=self.window.cache_store.validate_export(path)
                if self.source and target.resolve()==self.source.resolve():raise ValueError('请选择缓存目录以外的新保存位置。')
                manifest=self.manifest
                def done():
                    self.window.cache_store.record_save(target,'video',manifest);self.window.load_gallery()
                if self.rgb_source or not self.source or self.video_export_pending:
                    from .video_io import encode_native_rgb,encode_pngs
                    rgb=self.rgb_source;frames=self.frames.copy();fps=round(self.fps);count=self.count
                    self.process_export(lambda cancel,emit:encode_native_rgb(rgb,target,fps,cancel,emit,frame_count=count) if rgb
                                        else encode_pngs(frames,target,fps,cancel),done)
                else:shutil.copyfile(self.source,target);done()
            except (OSError,ValueError) as exc:self.window.add_chat('软件','保存动画失败：'+str(exc))
