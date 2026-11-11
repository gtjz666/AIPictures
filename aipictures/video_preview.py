"""Preview every source frame at source FPS; extraction is an explicit separate action."""
import json
import shutil
from pathlib import Path

from .playback_button import PlaybackButton
from PySide6.QtCore import QTimer,Qt,QUrl
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
        from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
        self.sound=QMediaPlayer(self);self.sound_output=QAudioOutput(self);self.sound_output.setVolume(.65)
        self.sound.setAudioOutput(self.sound_output);self.audio_source=None;self.silent_source=None;self.has_audio=False

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
        self.audio_source=Path(data['audio']) if data.get('audio') else None
        self.silent_source=Path(data['silent_video']) if data.get('silent_video') else None
        self.has_audio=bool(self.audio_source and self.audio_source.is_file())
        if not self.has_audio and not self.video_export_pending and self.source and self.source.is_file():
            import av
            with av.open(str(self.source)) as container:self.has_audio=bool(container.streams.audio)
        playable=self.audio_source if self.audio_source and self.audio_source.is_file() else self.source
        self.sound.setSource(QUrl.fromLocalFile(str(playable)) if self.has_audio else QUrl())
        self.fps=float(data['fps']);self.index=0
        if hasattr(self.window,'short_video'):self.window.short_video.continue_video(self.manifest)
        from .seed_controls import from_folder
        from_folder(self.window,self.manifest.parent)
        self.window.animation_player.stop();self.window.sequence_preview.clear_sequence()
        self.slider.setRange(0,self.count-1);self.seek(0);self.show()
        self.play.set_playing(True);self.timer.start(max(1,round(1000/self.fps)))
        if self.has_audio:self.sound.play()

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
        w.caption.setText('视频预览 · 导出可分别保存音频与画面' if self.has_audio else '完整动画预览 · 导出可自主选择动画帧');w.fit_preview()
        self.label.setText(f'{index+1}/{self.count} · {index/self.fps:.2f}s')
        if self.has_audio and abs(self.sound.position()-round(index/self.fps*1000))>120:
            self.sound.setPosition(round(index/self.fps*1000))

    def advance(self):
        if not self.window.preview.isVisible() or self.window.isMinimized():
            self.timer.stop();self.sound.pause();self.play.set_playing(False);return
        if self.has_audio:
            position=self.sound.position()/1000
            if position>=self.count/self.fps-.02:
                if not self.loop.isChecked():self.timer.stop();self.sound.pause();self.play.set_playing(False,replay=True);return
                self.sound.setPosition(0);self.sound.play();position=0
            self.slider.setValue(min(self.count-1,int(position*self.fps)));return
        if not self.loop.isChecked() and self.index==self.count-1:self.timer.stop();self.play.set_playing(False,replay=True);return
        self.slider.setValue((self.index+1)%self.count)

    def stop(self):
        self.timer.stop();self.play.set_playing(False);self.hide()
        if hasattr(self,'sound'):self.sound.stop();self.sound.setSource(QUrl())
        self.window.image_save.show();self.window.image_reuse.show()

    def toggle(self):
        if self.has_audio and self.sound.source().isEmpty():
            playable=self.audio_source if self.audio_source and self.audio_source.is_file() else self.source
            if playable:self.sound.setSource(QUrl.fromLocalFile(str(playable)));self.sound.setPosition(round(self.index/self.fps*1000))
        if self.timer.isActive():self.timer.stop();self.sound.pause();self.play.set_playing(False)
        elif self.count:
            if self.index==self.count-1:self.slider.setValue(0)
            self.timer.start(max(1,round(1000/self.fps)));self.play.set_playing(True)
            if self.has_audio:self.sound.play()

    def reset(self):
        self.stop();self.manifest=None;self.source=None;self.frames=[];self.rgb_source=None;self.count=0

    def choose_export(self):
        menu=QMenu(self)
        menu.addAction('完整视频…',self.save)
        if self.has_audio:
            menu.addAction('仅画面（无声视频）…',lambda:self.export_tracks('video'))
            menu.addAction('仅音频（WAV）…',lambda:self.export_tracks('audio'))
            menu.addAction('音画分别导出…',lambda:self.export_tracks('both'))
        menu.addAction('动画帧／精灵图…',self.split)
        menu.exec(self.extract.mapToGlobal(self.extract.rect().bottomLeft()))

    def process_export(self,action,done):
        w=self.window
        if w.current or w.pending or w.preparing or w.cache_busy:
            w.status.setText('请等当前任务结束后再导出。');return
        self.timer.stop();self.play.set_playing(False)
        self.sound.pause()
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
            self.timer.stop();self.sound.pause();self.play.set_playing(False)
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
                if (self.rgb_source or not self.source or self.video_export_pending) and not (self.has_audio and self.source):
                    from .video_io import encode_native_rgb,encode_pngs
                    rgb=self.rgb_source;frames=self.frames.copy();fps=round(self.fps);count=self.count
                    self.process_export(lambda cancel,emit:encode_native_rgb(rgb,target,fps,cancel,emit,frame_count=count) if rgb
                                        else encode_pngs(frames,target,fps,cancel),done)
                else:shutil.copyfile(self.source,target);done()
            except (OSError,ValueError) as exc:self.window.add_chat('软件','保存动画失败：'+str(exc))

    def export_tracks(self,kind):
        if not self.manifest or not self.has_audio:return
        from uuid import uuid4
        w=self.window
        if kind=='both':
            directory=QFileDialog.getExistingDirectory(self,'选择音画分离保存目录')
            if not directory:return
            directory=Path(directory)/('AlI_'+uuid4().hex[:8])
            targets={'video':directory/'video.mp4','audio':directory/'soundtrack.wav'}
        else:
            suffix='.wav' if kind=='audio' else '.mp4'
            path,_=QFileDialog.getSaveFileName(self,'导出音频' if kind=='audio' else '导出无声视频','soundtrack.wav' if kind=='audio' else 'video_silent.mp4','媒体 (*'+suffix+')')
            if not path:return
            targets={kind:Path(path)}
        try:
            targets={k:w.cache_store.validate_export(str(p)) for k,p in targets.items()}
            source=self.source;audio=self.audio_source;silent=self.silent_source;manifest=self.manifest
            def run(cancel,emit):
                nonlocal audio,silent
                if not audio or not silent:
                    from .video_audio import separate
                    scratch=manifest.parent/('separated_'+uuid4().hex[:8]);scratch.mkdir()
                    silent=scratch/'video.mp4';audio=scratch/'soundtrack.wav'
                    separate(source,silent,audio,cancel)
                for k,dst in targets.items():
                    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(audio if k=='audio' else silent,dst)
            def done():
                for k,dst in targets.items():w.cache_store.record_save(dst,'audio' if k=='audio' else 'video',manifest)
                w.load_gallery()
            self.process_export(run,done)
        except (OSError,ValueError) as exc:w.add_chat('软件','音画导出未完成：'+str(exc))
