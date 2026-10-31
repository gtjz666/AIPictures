"""Loop playback, scrubbing and portable local sequence export."""
import json
import zipfile
from pathlib import Path
from .animation_actions import ONE_SHOT_ACTIONS
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap,QPainter
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSlider, QFileDialog, QMessageBox,QCheckBox


class AnimationPlayer(QWidget):
    def __init__(self, window):
        super().__init__(window); self.window = window; self.frames=[]; self.index=0; self.manifest=None
        layout = QHBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.play = QPushButton('暂停'); self.play.clicked.connect(self.toggle); layout.addWidget(self.play)
        self.slider = QSlider(Qt.Orientation.Horizontal); self.slider.valueChanged.connect(self.seek); layout.addWidget(self.slider,1)
        self.label = QLabel(); layout.addWidget(self.label)
        self.physics=QCheckBox('游戏位移预览');self.physics.setToolTip('仅在预览中平移跳跃帧。导出 PNG 不烘焙轨迹，由游戏引擎控制角色移动。')
        self.physics.toggled.connect(lambda _:self.seek(self.index));layout.addWidget(self.physics);self.physics.hide()
        export = QPushButton('导出动画…'); export.clicked.connect(self.export); layout.addWidget(export)
        self.pixel_export = QPushButton('导出像素素材…')
        self.pixel_export.setToolTip('像素捕捉、锚点归一化、共享调色板和精灵图；不混合前后帧，原始帧保留。')
        self.pixel_export.clicked.connect(self.export_pixels); layout.addWidget(self.pixel_export)
        self.timer = QTimer(self); self.timer.timeout.connect(self.advance)

    def load(self,path):
        path=Path(path); manifest=json.loads(path.read_text('utf-8'))
        if manifest.get('status') != 'completed': raise ValueError('此序列尚未完成，部分帧可在结果目录查看')
        frames=[path.parent/item['image'] for item in manifest['frames']]
        if not frames or any(not item.is_file() for item in frames): raise ValueError('序列图片缺失')
        self.stop(); self.manifest=path; self.frames=frames; self.fps=manifest['fps']; self.index=0
        self.title=manifest.get('title','行走动画')
        self.action=manifest.get('action','walk')
        self.loop=manifest.get('loop',self.action not in ONE_SHOT_ACTIONS)
        self.game_data=manifest.get('game_animation')
        self.physics.blockSignals(True);self.physics.setChecked(False);self.physics.blockSignals(False)
        self.physics.setVisible(bool(self.game_data and self.game_data.get('engine_driven_jump')))
        self.slider.setRange(0,len(frames)-1); self.seek(0); self.show()
        self.window.sequence_preview.load(manifest,path.parent)
        self.play.setText('暂停'); self.timer.start(round(1000/self.fps))

    def stop(self):
        self.timer.stop(); self.hide()

    def reset(self):
        self.stop(); self.frames=[]; self.manifest=None; self.index=0

    def toggle(self):
        if self.timer.isActive(): self.timer.stop(); self.play.setText('播放')
        elif self.frames:
            if not self.loop and self.index==len(self.frames)-1:self.slider.setValue(0)
            self.timer.start(round(1000/self.fps)); self.play.setText('暂停')

    def advance(self):
        if not self.loop and self.index==len(self.frames)-1:
            self.timer.stop();self.play.setText('重播');return
        self.slider.setValue((self.index+1)%len(self.frames))

    def seek(self,index):
        if not self.frames: return
        self.window.preview.set_clickable(False)
        self.index=index; self.window.pixmap=QPixmap(str(self.frames[index])); self.window.output=str(self.frames[index])
        if self.physics.isChecked() and self.game_data and self.game_data.get('engine_driven_jump'):
            settings=self.game_data['preview_only'];source=self.window.pixmap
            canvas=QPixmap(source.width(),source.height()+settings['top_padding']);canvas.fill(Qt.GlobalColor.transparent)
            painter=QPainter(canvas);painter.drawPixmap(0,settings['top_padding']+settings['offset_y'][index],source);painter.end()
            self.window.pixmap=canvas
        self.window.preview_path=str(self.frames[index]); self.window.preview_role='animation'
        self.window.fit_preview(); self.label.setText(f'{index+1}/{len(self.frames)} · {self.fps} FPS')
        self.window.caption.setText(getattr(self,'title','动作动画'))

    def export(self):
        if not self.manifest: return
        if self.window.cache_busy: self.window.status.setText('请等待缓存清理结束后再导出。'); return
        path,_=QFileDialog.getSaveFileName(self,'导出 PNG 序列、精灵图和 GIF',getattr(self,'action','walk')+'-animation.zip','ZIP (*.zip)')
        if not path: return
        try:
            manifest=json.loads(self.manifest.read_text('utf-8'))
            files=self.frames+[self.manifest.parent/manifest['exports']['sprite_sheet'],self.manifest.parent/manifest['exports']['gif']]
            for key in ('game_metadata','game_preview_gif'):
                if manifest['exports'].get(key):files.append(self.manifest.parent/manifest['exports'][key])
            target=self.window.cache_store.validate_export(path)
            if target.resolve() in {p.resolve() for p in files}: raise ValueError('导出位置不能覆盖原始帧')
            portable={'schema_version':1,'fps':manifest['fps'],'frame_count':len(self.frames),'loop':self.loop,
                      'canvas':manifest['canvas'],'frames':[p.name for p in self.frames],
                      'exports':manifest['exports'],'direction':manifest['intent']['direction'],'action':manifest.get('action','walk')}
            if manifest.get('game_animation'):portable['game_animation']=manifest['game_animation']
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
                for file in files: archive.write(file,file.name)
                archive.writestr('animation.json',json.dumps(portable,ensure_ascii=False,indent=2))
            self.window.cache_store.record_save(target,'animation',self.manifest); self.window.load_gallery()
            self.window.add_chat('软件','已导出 PNG 序列、透明精灵图和 GIF：'+str(target))
        except (OSError,ValueError) as exc: QMessageBox.warning(self,'导出失败',str(exc))

    def export_pixels(self):
        from .sprite_export import start_export
        start_export(self)
