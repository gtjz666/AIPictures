"""Animation workspace: playback, all frame thumbnails, and assembled sheet."""
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QTabWidget, QLabel, QListWidget, QListWidgetItem, QAbstractItemView
from .transparent_preview import TransparentPreview


class SequencePreview(QTabWidget):
    def __init__(self, preview, window):
        super().__init__(); self.window=window; self.sheet_pixmap=QPixmap()
        self.addTab(preview,'画面 / 动画播放')
        self.frames=QListWidget(); self.frames.setViewMode(QListWidget.ViewMode.IconMode)
        self.frames.setResizeMode(QListWidget.ResizeMode.Adjust); self.frames.setMovement(QListWidget.Movement.Static)
        self.frames.setIconSize(QSize(126,168)); self.frames.setGridSize(QSize(156,204))
        self.frames.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.addTab(self.frames,'全部动画帧')
        self.sheet=TransparentPreview(); self.sheet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sheet.setMinimumSize(200,200); self.addTab(self.sheet,'精灵图')
        self.frames.itemClicked.connect(self.select_frame)
        self.currentChanged.connect(lambda _: self.fit_sheet())
        self.clear_sequence()

    def clear_sequence(self):
        self.setCurrentIndex(0)
        self.setTabEnabled(1,False); self.setTabEnabled(2,False)

    def load(self,manifest,folder):
        self.frames.clear(); folder=Path(folder)
        for entry in manifest['frames']:
            item=QListWidgetItem(QIcon(str(folder/entry['image'])),f'{entry["index"]+1:02d} · {entry["stage"]}')
            item.setData(Qt.ItemDataRole.UserRole,entry['index']); self.frames.addItem(item)
        self.sheet_pixmap=QPixmap(str(folder/'sprite_sheet.png'))
        self.setTabEnabled(1,True); self.setTabEnabled(2,True); self.fit_sheet()

    def select_frame(self,item):
        player=self.window.animation_player
        if player.timer.isActive(): player.toggle()
        player.slider.setValue(item.data(Qt.ItemDataRole.UserRole)); self.setCurrentIndex(0)

    def fit_sheet(self):
        if not self.sheet_pixmap.isNull():
            self.sheet.setPixmap(self.sheet_pixmap.scaled(self.sheet.size(),Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self,event):
        super().resizeEvent(event); self.fit_sheet()
