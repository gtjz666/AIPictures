"""A separate, animation-only motion source; never replaces the character image."""
import math
import threading
from pathlib import Path
from uuid import uuid4

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDoubleSpinBox,QFileDialog,QDialog,QComboBox,QInputDialog,QCheckBox,QGridLayout,QSlider,QSpinBox

from . import motion_guide as motion_reference
from .storage import write_json
from .frame_motion_input import copy_source


class MotionReferencePanel(QWidget):
    changed = Signal()

    def __init__(self, window, seconds):
        super().__init__(window);self.window=window;self.seconds=seconds;self.path=None;self.meta=None
        self.preview_paths=[];self.preview_dialog=None;self.preview_fps=24.;self.preview_offset=0.
        self.seek_cancel=threading.Event();self.seek_token=0
        self.seek_timer=QTimer(self);self.seek_timer.setSingleShot(True);self.seek_timer.timeout.connect(self.seek_outside_preview)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,3,0,3);layout.setSpacing(4)
        self.setObjectName('motionReference')
        self.asset_header=QWidget();row=QHBoxLayout(self.asset_header);row.setContentsMargins(0,0,0,0)
        self.poster=QLabel();self.poster.setFixedSize(44,44);self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.poster);self.summary=QLabel()
        self.summary.setWordWrap(True);row.addWidget(self.summary,1)
        layout.addWidget(self.asset_header);buttons=QGridLayout();layout.addLayout(buttons);self.buttons=buttons
        self.add=QPushButton('参考动画');self.add.clicked.connect(self.choose);buttons.addWidget(self.add,0,0)
        self.add_frames=QPushButton('动作帧');self.add_frames.clicked.connect(self.choose_frames);buttons.addWidget(self.add_frames,0,1)
        self.play=QPushButton('预览');self.play.clicked.connect(self.preview);buttons.addWidget(self.play,1,0)
        self.remove=QPushButton('移除');self.remove.clicked.connect(self.clear);buttons.addWidget(self.remove,1,1)
        self.range_dialog=QDialog(window);self.range_dialog.setWindowTitle('动作参考片段');self.range_dialog.resize(480,260)
        timeline=QVBoxLayout(self.range_dialog);timeline.addWidget(QLabel('动作起点（秒）'))
        self.range_button=QPushButton('时间轴');self.range_button.clicked.connect(self.range_dialog.show);buttons.addWidget(self.range_button,1,2)
        self.start=QDoubleSpinBox();self.start.setRange(0,0);self.start.setDecimals(6);self.start.setSingleStep(.1)
        self.start_note=QLabel('起点 0.000 秒')
        timeline.addWidget(self.start)
        self.range_slider=QSlider(Qt.Orientation.Horizontal);self.range_slider.setRange(0,1000);timeline.addWidget(self.range_slider)
        self.range_slider.valueChanged.connect(self.select_start)
        self.range_note=QLabel();self.range_note.setWordWrap(True);timeline.addWidget(self.range_note,1)
        self.frame_rate_row=QWidget();rate=QHBoxLayout(self.frame_rate_row);rate.setContentsMargins(0,0,0,0)
        rate.addWidget(QLabel('FPS'));self.frame_rate=QDoubleSpinBox();self.frame_rate.setRange(1,120);self.frame_rate.setDecimals(3);self.frame_rate.setValue(24)
        rate.addWidget(self.frame_rate);timeline.addWidget(self.frame_rate_row)
        self.frame_rate.editingFinished.connect(self.change_frame_rate)
        self.detail=QComboBox()
        for title,value in [('动作参考 · 512',512),('更精细 · 768',768),('高精细 · 1024',1024)]:self.detail.addItem(title,value)
        for i in (1,2):
            self.detail.model().item(i).setEnabled(False)
            self.detail.model().item(i).setToolTip('当前设备尚未通过此尺寸的真实生成验证。')
        self.detail.setToolTip('只改变动作参考的编码尺寸，人物参考和输出分辨率不变。高值需要更多资源，可能无法在当前设备运行。')
        timeline.addWidget(self.detail)
        self.repeat=QCheckBox('循环参考动作');self.repeat.toggled.connect(self.update_range);timeline.addWidget(self.repeat)
        self.start.valueChanged.connect(self.update_range);seconds.valueChanged.connect(self.update_range)
        self.clear()

    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'添加动作参考','','动画 (*.mp4 *.gif *.mkv *.mov *.webm *.avi)')
        if path:self.set_file(Path(path))

    def choose_frames(self):
        names,_=QFileDialog.getOpenFileNames(self.window,'选择PNG动作帧，按文件名排序','','动作帧 (*.png)')
        if not names:return
        fps,ok=QInputDialog.getInt(self.window,'动作帧率','每秒播放帧数（FPS）',24,1,120)
        if ok:self.set_frames([Path(p) for p in names],fps)

    def set_frames(self,paths,fps):
        from .frame_motion_input import import_frames
        self.set_file(None,frame_input=(paths,fps),frame_importer=import_frames)

    def set_folder(self,path):
        self.set_file(None,frame_folder=Path(path))

    def is_frames(self):
        return bool(self.path and self.path.suffix.lower()=='.json')

    def cancel_preview(self):
        self.seek_timer.stop();self.seek_cancel.set();self.seek_token+=1

    def select_start(self,value):
        if not self.path:return
        seconds=value/self.meta['frame_fps'] if self.is_frames() else value/1000
        self.start.setValue(seconds)
        index=round((seconds-self.preview_offset)*self.preview_fps)
        if 0<=index<len(self.preview_paths):
            self.cancel_preview()
            if hasattr(self.window,'workbench'):self.window.workbench.show_motion_reference(position=index)
        else:self.seek_timer.start(140)

    def seek_outside_preview(self):
        if not self.path or self.is_frames():return
        self.cancel_preview();token=self.seek_token;self.seek_cancel=threading.Event()
        cancel=self.seek_cancel;source=self.path;start=self.start.value();w=self.window
        folder=source.parent/'seek_preview'/uuid4().hex;duration=self.meta['duration']
        def prepare(emit):
            return motion_reference.prepare(source,folder,max(1.,min(4.,duration-start)),start,cancel,
                max_side=512,encode_video=False,save_frames=True,allow_tail_hold=True)
        def done(kind,data):
            if token!=self.seek_token or self.path!=source or getattr(w,'_closing',False):return
            if kind=='result':
                self.preview_paths=data['preview_frames'];self.preview_offset=start;self.preview_fps=24.
                w.workbench.show_motion_reference()
            elif kind=='error':w.status.setText('参考预览未完成：'+str(data))
        w.launch(prepare,done)

    def change_frame_rate(self):
        if not self.path or self.path.suffix.lower()!='.json':return
        if self.window.preparing:
            self.frame_rate.setValue(self.meta.get('frame_fps',24));return
        try:
            data,paths=motion_reference.sequence(self.path)
            if not math.isclose(self.frame_rate.value(),data['fps'],abs_tol=.0005):self.set_frames(paths,self.frame_rate.value())
        except (OSError,ValueError) as exc:
            self.frame_rate.setValue(self.meta.get('frame_fps',24));self.window.status.setText('帧率修改未完成：'+str(exc))

    def set_file(self,path,*,frame_input=None,frame_importer=None,frame_folder=None):
        w=self.window
        if w.preparing:
            w.status.setText('请等待当前素材准备完成。');return
        self.cancel_preview()
        if hasattr(w,'workbench'):w.intent_controller.animation_mode()
        w.preparing=True;w.prepare_cancel.clear();self.add.setEnabled(False);self.add_frames.setEnabled(False);self.remove.setEnabled(False)
        w.generate_button.setEnabled(False);w.status.setText('正在准备动作参考…')
        track_progress=w.current is None
        if track_progress:w.task_display.start();w.progress.setRange(0,0)
        folder=w.api_controller.data/'references'/'motion'/uuid4().hex
        folder.mkdir(parents=True)
        def prepare(emit):
            if frame_folder:
                from .frame_motion_input import folder_frames,import_frames
                paths,fps=folder_frames(frame_folder)
                frozen,meta=import_frames(paths,fps,folder,w.prepare_cancel)
                meta['frame_fps']=fps;path_for_name=frame_folder.name
            elif frame_input:
                frozen,meta=frame_importer(*frame_input,folder,w.prepare_cancel)
                meta['frame_fps']=frame_input[1]
                path_for_name='动作帧序列 · '+str(meta['frame_count'])+'帧'
            else:
                meta=motion_reference.inspect(path,w.prepare_cancel)
                frozen=folder/('source'+Path(path).suffix.lower())
                copy_source(Path(path),frozen,w.prepare_cancel)
                path_for_name=Path(path).name
            if frozen.suffix.lower()=='.json':
                frames_data,paths=motion_reference.sequence(frozen)
                preview=dict(preview_frames=[str(p) for p in paths],source=meta)
            else:preview=motion_reference.prepare(frozen,folder/'preview',max(1.,min(4.,meta['duration'])),0.,w.prepare_cancel,emit,max_side=512)
            if meta['sha256']!=preview['source']['sha256']:raise ValueError('导入期间原动作文件变化，请重新选择。')
            write_json(folder/'asset.json',dict(meta,name=path_for_name))
            return dict(path=str(frozen),meta=dict(meta,name=path_for_name),preview=preview)
        def event(kind,data):
            if kind=='video_stage':w.status.setText(data['message'])
            elif kind in ('result','error','cancelled'):
                w.preparing=False;self.add.setEnabled(True);self.add_frames.setEnabled(True);self.remove.setEnabled(bool(self.path))
                if track_progress:
                    w.progress.setRange(0,100);w.progress.setValue(100 if kind=='result' else 0)
                    w.task_display.finish('completed' if kind=='result' else 'cancelled' if kind=='cancelled' else 'failed')
                if kind=='result':
                    self.path=Path(data['path']);self.meta=data['meta'];self.preview_paths=data['preview']['preview_frames']
                    self.preview_fps=self.meta.get('frame_fps',24.);self.preview_offset=0.
                    self.frame_rate.setValue(self.meta.get('frame_fps',24))
                    self.summary.setText(f"{self.meta['name']} · {self.meta['duration']:.2f}s");self.summary.show()
                    self.poster.setPixmap(QPixmap(self.preview_paths[0]).scaled(self.poster.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
                    self.poster.show()
                    self.start.setMaximum(max(0.,self.meta['duration']-1/self.preview_fps));self.start.setValue(0.)
                    self.seconds.setValue(max(2.,math.floor(self.meta['duration']*1000)/1000))
                    self.repeat.setChecked(self.meta['duration']<2.)
                    self.play.setEnabled(True);self.remove.setEnabled(True);self.update_range();self.changed.emit()
                    if frame_folder and hasattr(w,'workbench'):w.workbench.show_motion_reference(play=True)
                    w.status.setText('动作参考已就绪')
                else:
                    self.frame_rate.setValue(self.meta.get('frame_fps',24) if self.meta else 24)
                    message='动作参考导入失败：'+str(data);w.status.setText(message);w.add_chat('软件',message)
                w.generation_type_changed();QTimer.singleShot(0,w.start_next)
        w.launch(prepare,event)

    def clear(self):
        self.cancel_preview()
        if self.preview_dialog:self.preview_dialog.close();self.preview_dialog=None
        self.range_dialog.close()
        self.path=None;self.meta=None;self.preview_paths=[];self.poster.clear()
        self.preview_fps=24.;self.preview_offset=0.
        self.poster.hide()
        self.repeat.setChecked(False)
        self.summary.clear();self.summary.hide()
        self.play.setEnabled(False);self.remove.setEnabled(False);self.start.setMaximum(0);self.start.setValue(0)
        self.update_range();self.changed.emit()

    def update_range(self,*_):
        self.frame_rate_row.setVisible(bool(self.path and self.path.suffix.lower()=='.json'))
        self.start.setEnabled(bool(self.path))
        self.detail.setEnabled(bool(self.path))
        self.range_button.setEnabled(bool(self.path));self.range_slider.setEnabled(bool(self.path))
        self.range_slider.blockSignals(True)
        if self.is_frames():
            self.range_slider.setRange(0,self.meta['frame_count']-1)
            value=round(self.start.value()*self.meta['frame_fps'])
            self.start_note.setText(f'起始帧 {value+1}/{self.meta["frame_count"]} · {self.start.value():.3f} 秒')
        else:
            self.range_slider.setRange(0,round(self.start.maximum()*1000));value=round(self.start.value()*1000)
            self.start_note.setText(f'起点 {self.start.value():.3f} 秒')
        self.range_slider.setValue(value)
        self.range_slider.blockSignals(False)
        if not self.meta:self.range_note.clear();return
        used=self.seconds.value() if self.repeat.isChecked() else min(self.seconds.value(),self.meta['duration']-self.start.value())
        text=f'参考 {self.start.value():.2f}–{self.start.value()+used:.2f}s'
        if self.seconds.value()>8:
            from .video_chain import plan
            parts=plan(self.seconds.value())
            text+=f' · {len(parts)}段 · 输出约 {parts[-1]["end"]:.2f}s'
        else:
            requested=math.ceil(self.seconds.value()*24)
            aligned=requested+(5-requested)%17
            text+=f' · 输出约 {aligned/24:.2f}s'
        self.range_note.setText(text)

    def preview(self):
        if not self.preview_paths:return
        if hasattr(self.window,'workbench'):
            self.window.workbench.show_motion_reference(play=True);return
        if self.preview_dialog:self.preview_dialog.close()
        dialog=QDialog(self.window);dialog.setWindowTitle('动作参考预览 · 前4秒');layout=QVBoxLayout(dialog)
        image=QLabel();image.setFixedSize(480,360);image.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(image)
        counter=QLabel();layout.addWidget(counter);button=QPushButton('暂停');layout.addWidget(button)
        timer=QTimer(dialog);index=[0];paths=self.preview_paths.copy()
        def draw():
            i=index[0];image.setPixmap(QPixmap(paths[i]).scaled(image.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            counter.setText(f'{i+1}/{len(paths)} 帧 · 24 FPS');index[0]=(i+1)%len(paths)
        def toggle():
            if timer.isActive():timer.stop();button.setText('播放')
            else:timer.start(42);button.setText('暂停')
        timer.timeout.connect(draw);button.clicked.connect(toggle);dialog.finished.connect(timer.stop)
        draw();timer.start(42);self.preview_dialog=dialog;dialog.show()
