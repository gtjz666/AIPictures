"""Loop playback, scrubbing and portable local sequence export."""
import json
import zipfile
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSlider, QFileDialog, QMessageBox


class AnimationPlayer(QWidget):
    def __init__(self, window):
        super().__init__(window); self.window = window; self.frames=[]; self.index=0; self.manifest=None
        layout = QHBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.play = QPushButton('暂停'); self.play.clicked.connect(self.toggle); layout.addWidget(self.play)
        self.slider = QSlider(Qt.Orientation.Horizontal); self.slider.valueChanged.connect(self.seek); layout.addWidget(self.slider,1)
        self.label = QLabel(); layout.addWidget(self.label)
        export = QPushButton('导出动画…'); export.clicked.connect(self.export); layout.addWidget(export)
        self.timer = QTimer(self); self.timer.timeout.connect(self.advance)

    def load(self,path):
        path=Path(path); manifest=json.loads(path.read_text('utf-8'))
        if manifest.get('status') != 'completed': raise ValueError('此序列尚未完成，部分帧可在结果目录查看')
        frames=[path.parent/item['image'] for item in manifest['frames']]
        if not frames or any(not item.is_file() for item in frames): raise ValueError('序列图片缺失')
        self.stop(); self.manifest=path; self.frames=frames; self.fps=manifest['fps']; self.index=0
        self.slider.setRange(0,len(frames)-1); self.seek(0); self.show()
        self.window.sequence_preview.load(manifest,path.parent)
        self.play.setText('暂停'); self.timer.start(round(1000/self.fps))

    def stop(self):
        self.timer.stop(); self.hide()

    def reset(self):
        self.stop(); self.frames=[]; self.manifest=None; self.index=0

    def toggle(self):
        if self.timer.isActive(): self.timer.stop(); self.play.setText('播放')
        elif self.frames: self.timer.start(round(1000/self.fps)); self.play.setText('暂停')

    def advance(self):
        self.slider.setValue((self.index+1)%len(self.frames))

    def seek(self,index):
        if not self.frames: return
        self.window.preview.set_clickable(False)
        self.index=index; self.window.pixmap=QPixmap(str(self.frames[index])); self.window.output=str(self.frames[index])
        self.window.preview_path=str(self.frames[index]); self.window.preview_role='animation'
        self.window.fit_preview(); self.label.setText(f'{index+1}/{len(self.frames)} · {self.fps} FPS')
        self.window.caption.setText('行走动画 · '+self.frames[index].parent.name)

    def export(self):
        if not self.manifest: return
        if self.window.cache_busy: self.window.status.setText('请等待缓存清理结束后再导出。'); return
        path,_=QFileDialog.getSaveFileName(self,'导出 PNG 序列、精灵图和 GIF','walk-animation.zip','ZIP (*.zip)')
        if not path: return
        try:
            manifest=json.loads(self.manifest.read_text('utf-8'))
            files=self.frames+[self.manifest.parent/'sprite_sheet.png',self.manifest.parent/'walk.gif']
            target=self.window.cache_store.validate_export(path)
            if target.resolve() in {p.resolve() for p in files}: raise ValueError('导出位置不能覆盖原始帧')
            portable={'schema_version':1,'fps':manifest['fps'],'frame_count':len(self.frames),
                      'canvas':manifest['canvas'],'frames':[p.name for p in self.frames],
                      'exports':manifest['exports'],'direction':manifest['intent']['direction']}
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
                for file in files: archive.write(file,file.name)
                archive.writestr('animation.json',json.dumps(portable,ensure_ascii=False,indent=2))
            self.window.cache_store.record_save(target,'animation',self.manifest); self.window.load_gallery()
            self.window.add_chat('软件','已导出 PNG 序列、透明精灵图和 GIF：'+str(target))
        except (OSError,ValueError) as exc: QMessageBox.warning(self,'导出失败',str(exc))
